package ru.sportcourts.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import ru.sportcourts.app.core.normalizeServerUrl
import ru.sportcourts.app.data.LatestReport
import ru.sportcourts.app.data.Venue
import ru.sportcourts.app.ui.Validation
import ru.sportcourts.app.ui.formatDistance
import ru.sportcourts.app.ui.initialsOf
import ru.sportcourts.app.ui.parseInstant
import ru.sportcourts.app.ui.playersNow
import ru.sportcourts.app.ui.plural

class LogicTest {
    @Test
    fun serverUrlIsNormalized() {
        assertEquals("https://abc.trycloudflare.com", normalizeServerUrl("abc.trycloudflare.com"))
        assertEquals("https://abc.trycloudflare.com", normalizeServerUrl("  https://abc.trycloudflare.com/  "))
        assertEquals("https://abc.trycloudflare.com", normalizeServerUrl("https://abc.trycloudflare.com/api/v1"))
        assertEquals("http://192.168.0.10:8000", normalizeServerUrl("http://192.168.0.10:8000"))
        assertNull(normalizeServerUrl(""))
        assertNull(normalizeServerUrl("ftp://example.com"))
    }

    @Test
    fun loginRules() {
        assertNotNull(Validation.login("ab"))
        assertNull(Validation.login("Alex_01"))
        assertNull(Validation.login("Алексей"))
        assertNotNull(Validation.login("bad login"))
        assertNotNull(Validation.login("a".repeat(33)))
    }

    @Test
    fun passwordRules() {
        assertNotNull(Validation.password("short"))
        assertNull(Validation.password("long-enough-1"))
        assertNotNull(Validation.password("x".repeat(129)))
    }

    @Test
    fun pluralsInRussian() {
        assertEquals("час", plural(1, "час", "часа", "часов"))
        assertEquals("часа", plural(3, "час", "часа", "часов"))
        assertEquals("часов", plural(5, "час", "часа", "часов"))
        assertEquals("часов", plural(11, "час", "часа", "часов"))
        assertEquals("часа", plural(22, "час", "часа", "часов"))
    }

    @Test
    fun distanceFormatting() {
        assertNull(formatDistance(null))
        assertEquals("350 м", formatDistance(0.35))
        assertEquals("3,8 км", formatDistance(3.8))
    }

    @Test
    fun timestampsFromServerParse() {
        assertNotNull(parseInstant("2026-10-30T22:14:22.286833Z"))
        assertNotNull(parseInstant("2026-10-30T22:14:22+00:00"))
        assertNull(parseInstant("не дата"))
        assertNull(parseInstant(null))
    }

    @Test
    fun initials() {
        assertEquals("АИ", initialsOf("Алиса Иванова"))
        assertEquals("А", initialsOf("алиса"))
        assertEquals("?", initialsOf("  "))
    }

    private fun venue(checked: Int, report: LatestReport?) = Venue(
        id = 1, name = "v", address = "a", latitude = 0.0, longitude = 0.0, venueType = "outdoor",
        checkedInCount = checked, latestReport = report,
    )

    @Test
    fun playersNowUsesFreshReportsOnly() {
        assertEquals(3, venue(3, null).playersNow())
        assertEquals(8, venue(3, LatestReport(8, "2026-10-30T22:00:00Z", isFresh = true)).playersNow())
        assertEquals(3, venue(3, LatestReport(8, "2026-10-30T22:00:00Z", isFresh = false)).playersNow())
        assertEquals(5, venue(5, LatestReport(2, "2026-10-30T22:00:00Z", isFresh = true)).playersNow())
    }
}
