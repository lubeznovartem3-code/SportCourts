package ru.sportcourts.app.core

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "sportcourts_prefs")

/** Локальные настройки (не секретные): тема, адрес сервера, опорная точка на карте. */
data class AppSettings(
    /** "light", "dark" или null — пока пользователь не выбирал (тогда как в системе). */
    val theme: String? = null,
    val apiUrl: String = "",
    val refLat: Double? = null,
    val refLon: Double? = null,
)

class Prefs(private val context: Context) {
    private object Keys {
        val theme = stringPreferencesKey("theme")
        val apiUrl = stringPreferencesKey("api_url")
        val refLat = doublePreferencesKey("ref_lat")
        val refLon = doublePreferencesKey("ref_lon")
    }

    val settings: Flow<AppSettings> = context.dataStore.data.map { it.toSettings() }

    private fun Preferences.toSettings() = AppSettings(
        theme = this[Keys.theme],
        apiUrl = this[Keys.apiUrl] ?: "",
        refLat = this[Keys.refLat],
        refLon = this[Keys.refLon],
    )

    suspend fun setTheme(theme: String) {
        context.dataStore.edit { it[Keys.theme] = theme }
    }

    suspend fun setApiUrl(url: String) {
        context.dataStore.edit { it[Keys.apiUrl] = url }
    }

    suspend fun setReferencePoint(lat: Double?, lon: Double?) {
        context.dataStore.edit {
            if (lat == null || lon == null) {
                it.remove(Keys.refLat)
                it.remove(Keys.refLon)
            } else {
                it[Keys.refLat] = lat
                it[Keys.refLon] = lon
            }
        }
    }
}
