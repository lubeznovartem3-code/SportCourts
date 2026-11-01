package ru.sportcourts.app.core

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import ru.sportcourts.app.data.Api
import ru.sportcourts.app.BuildConfig
import ru.sportcourts.app.data.HealthResponse
import ru.sportcourts.app.data.Me
import ru.sportcourts.app.data.UnreadCounts
import java.util.concurrent.TimeUnit

sealed interface Session {
    data object Loading : Session
    data object LoggedOut : Session
    /** Токен сохранён, но сервер сейчас недоступен: показываем экран «Нет связи» с повтором и сменой адреса. */
    class Unreachable(val message: String) : Session
    class In(val me: Me) : Session
}

/** Ручной контейнер зависимостей: один экземпляр на процесс, создаётся в [ru.sportcourts.app.SportCourtsApp]. */
class AppContainer(private val context: Context) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
        encodeDefaults = true
    }

    val prefs = Prefs(context)
    val vault = TokenVault(context)
    val serverConfig = ServerConfig()

    private val _settings = MutableStateFlow<AppSettings?>(null)
    /** null — настройки ещё читаются с диска. */
    val settings: StateFlow<AppSettings?> = _settings

    private val _session = MutableStateFlow<Session>(Session.Loading)
    val session: StateFlow<Session> = _session

    /** Сообщение на экране входа (например, «Сессия завершена»). */
    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice

    private val _unread = MutableStateFlow(UnreadCounts())
    val unread: StateFlow<UnreadCounts> = _unread

    private val okHttp: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .callTimeout(40, TimeUnit.SECONDS)
        .addInterceptor(BaseUrlInterceptor(serverConfig))
        .addInterceptor(AuthInterceptor({ vault.load() }) { message -> onSessionInvalid(message) })
        .build()

    val api: Api = Retrofit.Builder()
        .baseUrl("http://localhost/api/v1/")
        .client(okHttp)
        .addConverterFactory(json.asConverterFactory("application/json; charset=UTF-8".toMediaType()))
        .build()
        .create(Api::class.java)

    val http: OkHttpClient get() = okHttp

    val repo = Repository(this)

    /** Читает настройки и восстанавливает сессию. Вызывается один раз при запуске. */
    suspend fun start() {
        val s = prefs.settings.first()
        val initial = s.apiUrl.ifBlank { normalizeServerUrl(BuildConfig.DEFAULT_API_URL) ?: "" }
        serverConfig.baseUrl = initial
        _settings.value = s.copy(apiUrl = initial)
        val token = vault.load()
        if (token == null || initial.isBlank()) {
            _session.value = Session.LoggedOut
            return
        }
        when (val r = repo.call { it.me() }) {
            is ApiResult.Ok -> _session.value = Session.In(r.value)
            is ApiResult.Fail -> {
                if (r.error.network || r.error.status >= 500) {
                    _session.value = Session.Unreachable(r.error.message)
                } else {
                    vault.clear()
                    _session.value = Session.LoggedOut
                }
            }
        }
    }

    /** Повторная попытка восстановить сессию (после смены адреса или появления сети). */
    suspend fun retryStart() {
        _session.value = Session.Loading
        start()
    }

    suspend fun setTheme(theme: String) {
        prefs.setTheme(theme)
        _settings.value = _settings.value?.copy(theme = theme)
    }

    suspend fun setServerUrl(url: String) {
        prefs.setApiUrl(url)
        serverConfig.baseUrl = url
        _settings.value = _settings.value?.copy(apiUrl = url)
    }

    suspend fun setReferencePoint(lat: Double?, lon: Double?) {
        prefs.setReferencePoint(lat, lon)
        _settings.value = _settings.value?.copy(refLat = lat, refLon = lon)
    }

    fun onAuthenticated(token: String, me: Me) {
        vault.save(token)
        _notice.value = null
        _session.value = Session.In(me)
    }

    fun updateMe(me: Me) {
        if (_session.value is Session.In) _session.value = Session.In(me)
    }

    fun updateUnread(c: UnreadCounts) {
        _unread.value = c
    }

    fun clearNotice() {
        _notice.value = null
    }

    /** Выход: сервер получает команду завершить сессию, локальный токен удаляется в любом случае. */
    fun logout() {
        scope.launch {
            repo.call { it.logout() }
            vault.clear()
            _unread.value = UnreadCounts()
            _session.value = Session.LoggedOut
        }
    }

    private fun onSessionInvalid(message: String) {
        scope.launch {
            if (_session.value is Session.In) {
                vault.clear()
                _unread.value = UnreadCounts()
                _notice.value = message
                _session.value = Session.LoggedOut
            }
        }
    }

    /** Проверка адреса сервера: GET {url}/health должен вернуть сервис SportCourts. */
    suspend fun checkServer(url: String): ApiResult<HealthResponse> = withContext(Dispatchers.IO) {
        safeApiCall(json) {
            val request = Request.Builder().url("$url/health").get().build()
            // без перехватчиков: проверяем именно введённый адрес, а не сохранённый
            val client = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS).readTimeout(10, TimeUnit.SECONDS).callTimeout(15, TimeUnit.SECONDS).build()
            client.newCall(request).execute().use { resp ->
                val text = resp.body.string()
                if (!resp.isSuccessful) throw ServerCheckException("Сервер ответил кодом ${resp.code}. Проверьте адрес.")
                val health = json.decodeFromString(HealthResponse.serializer(), text)
                if (health.service != "sportcourts") throw ServerCheckException("По этому адресу находится не сервер SportCourts.")
                health
            }
        }
    }
}
