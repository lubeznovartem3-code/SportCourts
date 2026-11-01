package ru.sportcourts.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiError
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.AppContainer
import ru.sportcourts.app.ui.components.ErrorState
import ru.sportcourts.app.ui.components.LoadingBox

val LocalContainer = staticCompositionLocalOf<AppContainer> { error("AppContainer не предоставлен") }

/** Короткие всплывающие сообщения внизу экрана. */
class Toaster {
    var message by mutableStateOf<String?>(null)
    fun show(text: String) {
        message = text
    }
}

val LocalToaster = staticCompositionLocalOf { Toaster() }

/** false — ключ MapKit не задан в local.properties при сборке. */
val LocalMapKitReady = staticCompositionLocalOf { false }

/** Действия оболочки приложения, нужные экранам: открыть меню, перейти, вернуться. */
class ShellActions(
    val openDrawer: () -> Unit,
    val navigate: (String) -> Unit,
    val back: () -> Unit,
)

val LocalShell = staticCompositionLocalOf<ShellActions> { error("ShellActions не предоставлены") }

sealed interface Load<out T> {
    data object Loading : Load<Nothing>
    class Ready<T>(val value: T) : Load<T>
    class Failed(val error: ApiError) : Load<Nothing>
}

/** Загрузчик данных экрана: состояние «загрузка / готово / ошибка» и повторная загрузка. */
class Loader<T>(private val scope: CoroutineScope) {
    var fetch: suspend () -> ApiResult<T> = { error("fetch не задан") }
    var state by mutableStateOf<Load<T>>(Load.Loading)
        private set
    private var job: Job? = null

    val value: T? get() = (state as? Load.Ready<T>)?.value

    /** silent — не показывать индикатор, если данные уже есть (обновление «на месте»). */
    fun load(silent: Boolean = false) {
        job?.cancel()
        if (!silent || state !is Load.Ready) state = Load.Loading
        job = scope.launch {
            when (val r = fetch()) {
                is ApiResult.Ok -> state = Load.Ready(r.value)
                is ApiResult.Fail -> if (!silent || state !is Load.Ready) state = Load.Failed(r.error)
            }
        }
    }

    fun set(v: T) {
        state = Load.Ready(v)
    }
}

@Composable
fun <T> rememberLoader(vararg keys: Any?, fetch: suspend () -> ApiResult<T>): Loader<T> {
    val scope = rememberCoroutineScope()
    val loader = remember(*keys) { Loader<T>(scope) }
    loader.fetch = fetch
    LaunchedEffect(loader) { loader.load() }
    return loader
}

@Composable
fun <T> LoadView(loader: Loader<T>, modifier: Modifier = Modifier, content: @Composable (T) -> Unit) {
    when (val s = loader.state) {
        is Load.Loading -> LoadingBox(modifier)
        is Load.Failed -> ErrorState(s.error, onRetry = { loader.load() }, modifier = modifier)
        is Load.Ready -> Box(modifier) { content(s.value) }
    }
}

/** Запускает запрос из обработчика нажатия; результат обрабатывается в [onResult] на главном потоке. */
fun <T> CoroutineScope.request(call: suspend () -> ApiResult<T>, onResult: (ApiResult<T>) -> Unit) {
    launch { onResult(call()) }
}

/** ViewModel с доступом к контейнеру зависимостей (без внешних библиотек DI). */
@Composable
inline fun <reified T : androidx.lifecycle.ViewModel> containerViewModel(crossinline build: (AppContainer) -> T): T {
    val container = LocalContainer.current
    return androidx.lifecycle.viewmodel.compose.viewModel(
        factory = object : androidx.lifecycle.ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <V : androidx.lifecycle.ViewModel> create(modelClass: Class<V>): V = build(container) as V
        }
    )
}
