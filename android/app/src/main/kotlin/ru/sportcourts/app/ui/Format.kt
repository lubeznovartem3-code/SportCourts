package ru.sportcourts.app.ui

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val ruLocale = Locale("ru")
private val timeFmt = DateTimeFormatter.ofPattern("HH:mm", ruLocale)
private val dateTimeFmt = DateTimeFormatter.ofPattern("d MMM, HH:mm", ruLocale)
private val dateFmt = DateTimeFormatter.ofPattern("d MMM yyyy", ruLocale)

fun parseInstant(s: String?): Instant? = if (s.isNullOrBlank()) null else try {
    OffsetDateTime.parse(s).toInstant()
} catch (e: Exception) {
    try { Instant.parse(s) } catch (e2: Exception) { null }
}

/** «Сегодня, 18:00» / «Завтра, 09:30» / «5 нояб., 18:00». */
fun formatGameTime(s: String?): String {
    val inst = parseInstant(s) ?: return ""
    val zone = ZoneId.systemDefault()
    val local = inst.atZone(zone)
    val today = LocalDate.now(zone)
    val time = local.format(timeFmt)
    return when (local.toLocalDate()) {
        today -> "Сегодня, $time"
        today.plusDays(1) -> "Завтра, $time"
        else -> local.format(dateTimeFmt)
    }
}

fun formatDateTime(s: String?): String {
    val inst = parseInstant(s) ?: return ""
    return inst.atZone(ZoneId.systemDefault()).format(dateTimeFmt)
}

fun formatDate(s: String?): String {
    val inst = parseInstant(s) ?: return ""
    return inst.atZone(ZoneId.systemDefault()).format(dateFmt)
}

fun formatClock(s: String?): String {
    val inst = parseInstant(s) ?: return ""
    return inst.atZone(ZoneId.systemDefault()).format(timeFmt)
}

/** Склонение: plural(5, "час", "часа", "часов"). */
fun plural(n: Int, one: String, few: String, many: String): String {
    val a = Math.abs(n) % 100
    val b = a % 10
    return when {
        a in 11..14 -> many
        b == 1 -> one
        b in 2..4 -> few
        else -> many
    }
}

/** «минуту назад», «2 часа назад» — для статуса «был в сети». */
fun formatAgo(s: String?): String {
    val inst = parseInstant(s) ?: return ""
    val mins = Duration.between(inst, Instant.now()).toMinutes().coerceAtLeast(0).toInt()
    return when {
        mins < 1 -> "только что"
        mins < 60 -> "$mins ${plural(mins, "минуту", "минуты", "минут")} назад"
        mins < 60 * 24 -> { val h = mins / 60; "$h ${plural(h, "час", "часа", "часов")} назад" }
        else -> { val d = mins / (60 * 24); if (d > 30) formatDate(s) else "$d ${plural(d, "день", "дня", "дней")} назад" }
    }
}

fun formatDistance(km: Double?): String? {
    if (km == null) return null
    return if (km < 1.0) "${(km * 1000).toInt().coerceAtLeast(10)} м" else String.format(ruLocale, "%.1f км", km)
}

/** Минуты до истечения отметки «Играю». */
fun minutesLeft(expiresAt: String?): Int? {
    val inst = parseInstant(expiresAt) ?: return null
    return Duration.between(Instant.now(), inst).toMinutes().toInt().coerceAtLeast(0)
}

fun venueTypeName(type: String): String = when (type) {
    "outdoor" -> "Открытая"
    "indoor" -> "Закрытая"
    else -> type
}

fun roleName(role: String): String = when (role) {
    "admin" -> "Администратор"
    "moderator" -> "Модератор"
    else -> "Пользователь"
}

fun initialsOf(name: String): String {
    val t = name.trim()
    if (t.isEmpty()) return "?"
    val parts = t.split(" ").filter { it.isNotEmpty() }
    return if (parts.size >= 2) "${parts[0].first()}${parts[1].first()}".uppercase() else t.take(1).uppercase()
}

/** Сколько людей на площадке: максимум из отметок «Играю» и свежего сообщения о числе игроков (как на сервере). */
fun ru.sportcourts.app.data.Venue.playersNow(): Int {
    val report = latestReport
    val reported = if (report != null && report.isFresh) report.playerCount else 0
    return maxOf(checkedInCount, reported)
}

/** Имя для показа в списках; «—», если пользователя нет. */
fun ru.sportcourts.app.data.UserBrief?.shownName(): String =
    if (this == null) "—" else displayName.ifEmpty { login }
