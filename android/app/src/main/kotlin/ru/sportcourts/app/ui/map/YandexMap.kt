package ru.sportcourts.app.ui.map

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.yandex.mapkit.Animation
import com.yandex.mapkit.geometry.Point
import com.yandex.mapkit.map.CameraPosition
import com.yandex.mapkit.map.InputListener
import com.yandex.mapkit.map.MapObjectCollection
import com.yandex.mapkit.map.MapObjectTapListener
import com.yandex.mapkit.map.PlacemarkMapObject
import com.yandex.mapkit.mapview.MapView
import com.yandex.runtime.image.ImageProvider
import ru.sportcourts.app.data.Venue
import ru.sportcourts.app.ui.playersNow
import com.yandex.mapkit.map.Map as YMap
import java.lang.ref.WeakReference

/** Рисуем маркеры сами (без файлов-картинок): круг с числом игроков. */
private object Markers {
    private val cache = HashMap<String, Bitmap>()

    private fun circle(context: Context, sizeDp: Float, fill: Int, ring: Int, text: String?): Bitmap {
        val d = context.resources.displayMetrics.density
        val px = (sizeDp * d).toInt().coerceAtLeast(8)
        val bmp = Bitmap.createBitmap(px, px, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val ringW = 3f * d
        paint.color = ring
        canvas.drawCircle(px / 2f, px / 2f, px / 2f, paint)
        paint.color = fill
        canvas.drawCircle(px / 2f, px / 2f, px / 2f - ringW, paint)
        if (text != null) {
            paint.color = 0xFFFFFFFF.toInt()
            paint.typeface = Typeface.DEFAULT_BOLD
            paint.textAlign = Paint.Align.CENTER
            paint.textSize = px * 0.42f
            val y = px / 2f - (paint.descent() + paint.ascent()) / 2f
            canvas.drawText(text, px / 2f, y, paint)
        }
        return bmp
    }

    fun venue(context: Context, players: Int, selected: Boolean): Bitmap {
        val key = "v$players$selected"
        return cache.getOrPut(key) {
            circle(context, if (selected) 46f else 38f, if (selected) 0xFF10B981.toInt() else 0xFF131A2B.toInt(), 0xFFFFFFFF.toInt(),
                if (players > 0) players.coerceAtMost(99).toString() else null)
        }
    }

    fun me(context: Context): Bitmap = cache.getOrPut("me") { circle(context, 20f, 0xFF2563EB.toInt(), 0xFFFFFFFF.toInt(), null) }
    fun reference(context: Context): Bitmap = cache.getOrPut("ref") { circle(context, 24f, 0xFFF59E0B.toInt(), 0xFFFFFFFF.toInt(), null) }
}

private class MapHolder {
    var view: MapView? = null
    var venueObjects: MapObjectCollection? = null
    var userMark: PlacemarkMapObject? = null
    var refMark: PlacemarkMapObject? = null
    var started = false

    // MapKit хранит слушателей по слабой ссылке — держим сильные ссылки здесь
    var tapListener: MapObjectTapListener? = null
    var inputListener: InputListener? = null
}

/** Карта Яндекса. Все изменения идут через состояние: площадки, выбранная, моё положение, точка отсчёта, тема. */
@Composable
fun YandexMap(
    venues: List<Venue>,
    selectedId: Long?,
    me: GeoPoint?,
    reference: GeoPoint?,
    dark: Boolean,
    camera: CameraRequest?,
    onSelect: (Venue) -> Unit,
    onLongTap: (GeoPoint) -> Unit,
    onEmptyTap: (GeoPoint) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val holder = remember { MapHolder() }
    val currentVenues = rememberUpdatedState(venues)
    val onSelectState = rememberUpdatedState(onSelect)
    val onLongTapState = rememberUpdatedState(onLongTap)
    val onEmptyTapState = rememberUpdatedState(onEmptyTap)

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            val view = MapView(ctx)
            holder.view = view
            val map = view.mapWindow.map
            holder.venueObjects = map.mapObjects.addCollection()
            holder.tapListener = MapObjectTapListener { obj, _ ->
                val id = obj.userData as? Long
                val venue = currentVenues.value.firstOrNull { it.id == id }
                if (venue != null) onSelectState.value(venue)
                true
            }
            holder.inputListener = object : InputListener {
                override fun onMapTap(map: YMap, point: Point) {
                    onEmptyTapState.value(GeoPoint(point.latitude, point.longitude))
                }

                override fun onMapLongTap(map: YMap, point: Point) {
                    onLongTapState.value(GeoPoint(point.latitude, point.longitude))
                }
            }
            map.addInputListener(WeakReference(holder.inputListener!!))
            if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
                view.onStart()
                holder.started = true
            }
            view
        },
    )

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> if (!holder.started) { holder.started = true; holder.view?.onStart() }
                Lifecycle.Event.ON_STOP -> if (holder.started) { holder.started = false; holder.view?.onStop() }
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            if (holder.started) { holder.started = false; holder.view?.onStop() }
        }
    }

    LaunchedEffect(dark) {
        holder.view?.mapWindow?.map?.isNightModeEnabled = dark
    }

    LaunchedEffect(venues, selectedId) {
        val collection = holder.venueObjects ?: return@LaunchedEffect
        collection.clear()
        val listener = holder.tapListener ?: return@LaunchedEffect
        for (v in venues) {
            val mark = collection.addPlacemark(Point(v.latitude, v.longitude))
            mark.setIcon(ImageProvider.fromBitmap(Markers.venue(context, v.playersNow(), v.id == selectedId)))
            mark.userData = v.id
            mark.zIndex = if (v.id == selectedId) 10f else 0f
            mark.addTapListener(WeakReference(listener))
        }
    }

    LaunchedEffect(me) {
        val map = holder.view?.mapWindow?.map ?: return@LaunchedEffect
        holder.userMark?.let { map.mapObjects.remove(it) }
        holder.userMark = null
        if (me != null) {
            val mark = map.mapObjects.addPlacemark(Point(me.lat, me.lon))
            mark.setIcon(ImageProvider.fromBitmap(Markers.me(context)))
            holder.userMark = mark
        }
    }

    LaunchedEffect(reference) {
        val map = holder.view?.mapWindow?.map ?: return@LaunchedEffect
        holder.refMark?.let { map.mapObjects.remove(it) }
        holder.refMark = null
        if (reference != null) {
            val mark = map.mapObjects.addPlacemark(Point(reference.lat, reference.lon))
            mark.setIcon(ImageProvider.fromBitmap(Markers.reference(context)))
            holder.refMark = mark
        }
    }

    LaunchedEffect(camera?.id) {
        val c = camera ?: return@LaunchedEffect
        val map = holder.view?.mapWindow?.map ?: return@LaunchedEffect
        map.move(CameraPosition(Point(c.lat, c.lon), c.zoom, 0f, 0f), Animation(Animation.Type.SMOOTH, 0.5f), null)
    }
}
