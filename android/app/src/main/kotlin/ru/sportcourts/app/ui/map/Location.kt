package ru.sportcourts.app.ui.map

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.util.Consumer

data class GeoPoint(val lat: Double, val lon: Double)

fun hasLocationPermission(context: Context): Boolean =
    ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

/**
 * Одноразовое определение положения без сервисов Google. Если определить не удалось
 * (геолокация выключена, нет разрешения, нет сигнала) — результат null, и приложение
 * использует точку отсчёта, выбранную пользователем, либо центр области с площадками.
 */
@SuppressLint("MissingPermission")
fun requestSingleLocation(context: Context, onResult: (GeoPoint?) -> Unit) {
    if (!hasLocationPermission(context)) { onResult(null); return }
    val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
    if (lm == null) { onResult(null); return }
    val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER).filter {
        try { lm.isProviderEnabled(it) } catch (e: Exception) { false }
    }
    if (providers.isEmpty()) { onResult(null); return }

    var lastKnown: Location? = null
    for (p in providers) {
        val l = try { lm.getLastKnownLocation(p) } catch (e: SecurityException) { null }
        if (l != null && (lastKnown == null || l.time > lastKnown!!.time)) lastKnown = l
    }
    val last = lastKnown
    if (last != null && System.currentTimeMillis() - last.time < 2 * 60 * 1000) {
        onResult(GeoPoint(last.latitude, last.longitude))
        return
    }

    var done = false
    val handler = Handler(Looper.getMainLooper())
    val signal = CancellationSignal()
    fun finish(l: Location?) {
        if (done) return
        done = true
        handler.removeCallbacksAndMessages(null)
        val use = l ?: last
        onResult(if (use != null) GeoPoint(use.latitude, use.longitude) else null)
    }
    handler.postDelayed({ signal.cancel(); finish(null) }, 8000)
    try {
        LocationManagerCompat.getCurrentLocation(
            lm, providers.first(), signal, ContextCompat.getMainExecutor(context),
            Consumer<Location?> { finish(it) },
        )
    } catch (e: Exception) {
        finish(null)
    }
}
