package ru.sportcourts.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.Response
import retrofit2.HttpException
import ru.sportcourts.app.data.ErrorEnvelope
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/** Ошибка API в виде, пригодном для показа пользователю. */
class ApiError(
    val code: String,
    val message: String,
    val status: Int = 0,
    /** true — запрос не дошёл до сервера (нет сети, неверный адрес, сервер выключен). */
    val network: Boolean = false,
)

sealed interface ApiResult<out T> {
    class Ok<T>(val value: T) : ApiResult<T>
    class Fail(val error: ApiError) : ApiResult<Nothing>
}

val ApiResult<*>.isOk get() = this is ApiResult.Ok

/** Текущий адрес сервера (без /api/v1), доступный сетевому слою из любого потока. */
class ServerConfig {
    @Volatile var baseUrl: String = ""
}

/** Приводит введённый адрес к виду scheme://host[:port]; null, если адрес некорректен. */
fun normalizeServerUrl(input: String): String? {
    var s = input.trim().trimEnd('/')
    if (s.isEmpty()) return null
    if (s.endsWith("/api/v1")) s = s.removeSuffix("/api/v1").trimEnd('/')
    if (!s.contains("://")) s = "https://$s"
    val url = s.toHttpUrlOrNull() ?: return null
    if (url.scheme != "http" && url.scheme != "https") return null
    val default = (url.scheme == "https" && url.port == 443) || (url.scheme == "http" && url.port == 80)
    return url.scheme + "://" + url.host + (if (default) "" else ":" + url.port)
}

/** Подставляет актуальный адрес сервера в каждый запрос (запросы Retrofit строятся на заглушке). */
class BaseUrlInterceptor(private val config: ServerConfig) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val target = config.baseUrl.toHttpUrlOrNull()
            ?: throw IOException("Адрес сервера не задан. Укажите его в настройках приложения.")
        val url = request.url.newBuilder().scheme(target.scheme).host(target.host).port(target.port).build()
        return chain.proceed(request.newBuilder().url(url).build())
    }
}

/** Добавляет токен и сообщает, если сервер перестал признавать сессию. */
class AuthInterceptor(
    private val token: () -> String?,
    private val onSessionInvalid: (String) -> Unit,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val sent = token()
        val builder = chain.request().newBuilder()
        if (sent != null) builder.header("Authorization", "Bearer $sent")
        val response = chain.proceed(builder.build())
        if (sent != null && (response.code == 401 || response.code == 403)) {
            val text = try { response.peekBody(8192).string() } catch (e: Exception) { "" }
            val dead = listOf("invalid_token", "not_authenticated", "account_disabled").firstOrNull { text.contains("\"$it\"") }
            if (dead != null) {
                val msg = if (dead == "account_disabled") "Аккаунт отключён администратором." else "Сессия завершена. Войдите заново."
                onSessionInvalid(msg)
            }
        }
        return response
    }
}

/** Адрес отвечает, но это не сервер SportCourts (проверка в настройках). */
class ServerCheckException(message: String) : IOException(message)

fun describeNetworkError(e: Throwable): String = when {
    e is ServerCheckException -> e.message ?: "Неверный адрес сервера."
    e is UnknownHostException -> "Не удаётся найти сервер. Проверьте адрес сервера в настройках и подключение к интернету."
    e is SocketTimeoutException -> "Сервер не отвечает (превышено время ожидания). Попробуйте ещё раз."
    e is ConnectException -> "Нет связи с сервером. Убедитесь, что сервер запущен, а адрес в настройках верен."
    e is SSLException -> "Не удалось установить защищённое соединение. Проверьте адрес сервера (https://…)."
    e.message?.contains("CLEARTEXT", ignoreCase = true) == true ->
        "Адрес должен начинаться с https://. Незащищённые подключения в этой сборке запрещены."
    e is IOException && e.message?.startsWith("Адрес сервера") == true -> e.message ?: "Адрес сервера не задан."
    else -> "Нет связи с сервером. Проверьте интернет и адрес сервера в настройках."
}

fun parseHttpError(e: HttpException, json: Json): ApiError {
    val status = e.code()
    val raw = try { e.response()?.errorBody()?.string() } catch (ex: Exception) { null }
    if (raw != null) {
        try {
            val body = json.decodeFromString(ErrorEnvelope.serializer(), raw).error
            if (body != null && body.message.isNotBlank()) return ApiError(body.code, body.message, status)
        } catch (ex: SerializationException) {
            // не наш формат ответа (например, страница шлюза) — ниже общее сообщение
        } catch (ex: IllegalArgumentException) {
        }
    }
    val msg = when (status) {
        502, 503, 504, 521, 522, 523, 530 -> "Сервер временно недоступен (код $status). Проверьте, что сервер и туннель запущены, а адрес в настройках верен."
        404 -> "Адрес не найден на сервере (код 404). Проверьте адрес сервера в настройках."
        else -> "Ошибка сервера (код $status)."
    }
    return ApiError("http_$status", msg, status)
}

suspend fun <T> safeApiCall(json: Json, block: suspend () -> T): ApiResult<T> = try {
    ApiResult.Ok(block())
} catch (e: CancellationException) {
    throw e
} catch (e: HttpException) {
    ApiResult.Fail(parseHttpError(e, json))
} catch (e: SerializationException) {
    ApiResult.Fail(ApiError("bad_response", "Сервер вернул неожиданный ответ. Возможно, версии приложения и сервера не совпадают.", 0))
} catch (e: IOException) {
    ApiResult.Fail(ApiError("network", describeNetworkError(e), 0, network = true))
} catch (e: IllegalArgumentException) {
    ApiResult.Fail(ApiError("bad_request", "Не удалось выполнить запрос: ${e.message ?: "неверные данные"}", 0))
}
