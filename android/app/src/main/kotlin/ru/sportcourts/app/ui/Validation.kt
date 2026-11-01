package ru.sportcourts.app.ui

/** Проверки на устройстве повторяют правила сервера (сервер всё равно проверяет заново). */
object Validation {
    private const val PUNCT = "_.-@+!#$%&*~"

    fun login(value: String): String? {
        val v = value.trim()
        if (v.length < 3 || v.length > 32) return "Логин: от 3 до 32 символов"
        if (!v.all { it.isLetterOrDigit() || it in PUNCT }) return "Логин: только буквы, цифры и символы _ . - @ + ! # $ % & * ~"
        return null
    }

    fun password(value: String): String? {
        if (value.length < 8) return "Пароль: не меньше 8 символов"
        if (value.length > 128) return "Пароль: не больше 128 символов"
        return null
    }

    fun displayName(value: String): String? {
        val v = value.trim()
        if (v.isEmpty()) return "Имя не может быть пустым"
        if (v.length > 64) return "Имя: не больше 64 символов"
        return null
    }
}
