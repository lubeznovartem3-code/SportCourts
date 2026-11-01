package ru.sportcourts.app.ui.map

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.AppContainer
import ru.sportcourts.app.data.Sport
import ru.sportcourts.app.data.Venue
import ru.sportcourts.app.ui.Load

class CameraRequest(val id: Int, val lat: Double, val lon: Double, val zoom: Float)

/** Состояние экрана карты живёт, пока экран в стеке навигации: фильтры и выбранная площадка не теряются. */
class MapViewModel(private val container: AppContainer, startInList: Boolean) : ViewModel() {
    var query by mutableStateOf("")
    var sportId by mutableStateOf<Int?>(null)
    var venueType by mutableStateOf<String?>(null)
    var minPlayers by mutableStateOf<Int?>(null)
    var sort by mutableStateOf("distance")

    var listMode by mutableStateOf(startInList)
    var searchOpen by mutableStateOf(false)
    var filtersOpen by mutableStateOf(false)

    var venues by mutableStateOf<Load<List<Venue>>>(Load.Loading)
    var sports by mutableStateOf<List<Sport>>(emptyList())

    /** Выбранная площадка (с подробностями, загруженными отдельным запросом). */
    var selected by mutableStateOf<Venue?>(null)

    /** Положение пользователя, если удалось определить. */
    var location by mutableStateOf<GeoPoint?>(null)
    var locationNote by mutableStateOf<String?>(null)

    var camera by mutableStateOf<CameraRequest?>(null)
    private var cameraCounter = 0
    private var job: Job? = null
    private var initialCameraDone = false

    val activeFilters: Int
        get() = listOfNotNull(sportId, venueType, minPlayers).size + (if (sort != "distance") 1 else 0)

    /** Точка отсчёта для расстояний: выбранная вручную, иначе положение пользователя. */
    fun origin(): GeoPoint? {
        val s = container.settings.value
        val lat = s?.refLat
        val lon = s?.refLon
        if (lat != null && lon != null) return GeoPoint(lat, lon)
        return location
    }

    fun moveCamera(lat: Double, lon: Double, zoom: Float = 14f) {
        camera = CameraRequest(++cameraCounter, lat, lon, zoom)
    }

    fun loadSports() {
        if (sports.isNotEmpty()) return
        viewModelScope.launch {
            val r = container.repo.call { it.sports() }
            if (r is ApiResult.Ok) sports = r.value.items.filter { it.isActive }
        }
    }

    fun reload(silent: Boolean = false) {
        job?.cancel()
        val o = origin()
        if (!silent || venues !is Load.Ready) venues = Load.Loading
        job = viewModelScope.launch {
            val r = container.repo.call {
                it.venues(
                    q = query.trim().ifEmpty { null }, sportId = sportId, venueType = venueType, minPlayers = minPlayers,
                    lat = o?.lat, lon = o?.lon, sort = sort,
                )
            }
            when (r) {
                is ApiResult.Ok -> {
                    venues = Load.Ready(r.value.items)
                    val sel = selected
                    if (sel != null) {
                        val fresh = r.value.items.firstOrNull { it.id == sel.id }
                        // список содержит только краткие данные: обновляем счётчики, сохраняя подробности
                        if (fresh != null) {
                            selected = sel.copy(
                                checkedInCount = fresh.checkedInCount, latestReport = fresh.latestReport,
                                openGamesCount = fresh.openGamesCount, distanceKm = fresh.distanceKm ?: sel.distanceKm,
                            )
                        }
                    }
                    if (!initialCameraDone && o == null && r.value.items.isNotEmpty()) {
                        initialCameraDone = true
                        val first = r.value.items.first()
                        moveCamera(first.latitude, first.longitude, 12f)
                    }
                }
                is ApiResult.Fail -> if (!silent || venues !is Load.Ready) venues = Load.Failed(r.error)
            }
        }
    }

    fun onLocation(p: GeoPoint?) {
        location = p
        if (p != null) {
            locationNote = null
            if (container.settings.value?.refLat == null) {
                moveCamera(p.lat, p.lon, 14f)
                initialCameraDone = true
            }
        } else {
            locationNote = "Геопозиция недоступна. Расстояния считаются от выбранной точки; задать её можно долгим нажатием на карте."
        }
        reload(silent = true)
    }

    fun select(v: Venue?) {
        selected = v
        if (v != null) {
            viewModelScope.launch {
                val o = origin()
                val r = container.repo.call { it.venue(v.id, o?.lat, o?.lon) }
                if (r is ApiResult.Ok && selected?.id == v.id) selected = r.value
            }
        }
    }

    fun setReferencePoint(p: GeoPoint?) {
        viewModelScope.launch {
            container.setReferencePoint(p?.lat, p?.lon)
            reload(silent = true)
        }
    }

    /** Открыть площадку по идентификатору (например, после одобрения заявки). */
    fun focusVenue(id: Long) {
        val v = (venues as? Load.Ready)?.value?.firstOrNull { it.id == id }
        if (v != null) {
            select(v)
            moveCamera(v.latitude, v.longitude, 15f)
        }
    }
}
