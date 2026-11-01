package ru.sportcourts.app.core

import ru.sportcourts.app.data.Api

/** Единая точка вызова API: превращает исключения в [ApiResult] с понятным текстом ошибки. */
class Repository(private val container: AppContainer) {
    val api: Api get() = container.api

    suspend fun <T> call(block: suspend (Api) -> T): ApiResult<T> = safeApiCall(container.json) { block(container.api) }

    /** Абсолютный адрес картинки: сервер отдаёт относительные пути вида /media/… */
    fun mediaUrl(path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http://") || path.startsWith("https://")) return path
        return container.serverConfig.baseUrl.trimEnd('/') + "/" + path.trimStart('/')
    }
}
