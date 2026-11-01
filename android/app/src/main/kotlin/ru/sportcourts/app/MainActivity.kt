package ru.sportcourts.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.yandex.mapkit.MapKitFactory
import ru.sportcourts.app.ui.AppRoot

class MainActivity : ComponentActivity() {
    private val app get() = application as SportCourtsApp

    override fun onCreate(savedInstanceState: Bundle?) {
        // Настоящая строка состояния Android остаётся на месте, приложение рисуется под ней (edge-to-edge)
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        if (app.mapKitReady) {
            try {
                MapKitFactory.initialize(this)
            } catch (e: Throwable) {
                // карта будет недоступна, остальное приложение работает
            }
        }
        setContent { AppRoot(app.container, app.mapKitReady) }
    }

    override fun onStart() {
        super.onStart()
        if (app.mapKitReady) {
            try { MapKitFactory.getInstance().onStart() } catch (e: Throwable) { }
        }
    }

    override fun onStop() {
        if (app.mapKitReady) {
            try { MapKitFactory.getInstance().onStop() } catch (e: Throwable) { }
        }
        super.onStop()
    }
}
