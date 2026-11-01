package ru.sportcourts.app

import android.app.Application
import com.yandex.mapkit.MapKitFactory
import ru.sportcourts.app.core.AppContainer

class SportCourtsApp : Application() {
    lateinit var container: AppContainer
        private set

    /** false — ключ MapKit не задан при сборке: карта показывает подсказку вместо падения. */
    var mapKitReady: Boolean = false
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(applicationContext)
        if (BuildConfig.MAPKIT_API_KEY.isNotBlank()) {
            try {
                MapKitFactory.setApiKey(BuildConfig.MAPKIT_API_KEY)
                mapKitReady = true
            } catch (e: Exception) {
                mapKitReady = false
            }
        }
    }
}
