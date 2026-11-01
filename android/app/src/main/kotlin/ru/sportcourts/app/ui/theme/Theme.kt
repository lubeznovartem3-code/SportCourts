package ru.sportcourts.app.ui.theme

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.background
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

/** Палитра приложения (взята из макета: тёмно-синие кнопки, светло-серые поля, зелёный «в сети»). */
class AppColors(
    val dark: Boolean,
    val background: Color,
    val surface: Color,      // поля ввода, плашки
    val border: Color,
    val text: Color,
    val textSecondary: Color,
    val primary: Color,      // основные кнопки
    val onPrimary: Color,
    val online: Color,
    val danger: Color,
    val bubbleOther: Color,
    val bubbleMine: Color,
    val onBubbleMine: Color,
    val scrim: Color,
    val mapPlaceholder: Color,
)

val LightColors = AppColors(
    dark = false,
    background = Color(0xFFFFFFFF),
    surface = Color(0xFFF3F4F6),
    border = Color(0xFFE5E7EB),
    text = Color(0xFF111827),
    textSecondary = Color(0xFF6B7280),
    primary = Color(0xFF131A2B),
    onPrimary = Color(0xFFFFFFFF),
    online = Color(0xFF10B981),
    danger = Color(0xFFDC2626),
    bubbleOther = Color(0xFFE5E7EB),
    bubbleMine = Color(0xFF131A2B),
    onBubbleMine = Color(0xFFFFFFFF),
    scrim = Color(0x99000000),
    mapPlaceholder = Color(0xFFE5E7EB),
)

val DarkColors = AppColors(
    dark = true,
    background = Color(0xFF0E131F),
    surface = Color(0xFF1A2132),
    border = Color(0xFF2A3347),
    text = Color(0xFFF3F4F6),
    textSecondary = Color(0xFF9CA3AF),
    primary = Color(0xFFE5E7EB),
    onPrimary = Color(0xFF111827),
    online = Color(0xFF34D399),
    danger = Color(0xFFF87171),
    bubbleOther = Color(0xFF232C41),
    bubbleMine = Color(0xFF3A4A72),
    onBubbleMine = Color(0xFFFFFFFF),
    scrim = Color(0xB3000000),
    mapPlaceholder = Color(0xFF1A2132),
)

val LocalColors = staticCompositionLocalOf { LightColors }

/** Размеры шрифтов. */
object AppType {
    val screenTitle = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
    val title = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
    val logo = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold)
    val body = TextStyle(fontSize = 15.sp)
    val bodyBold = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    val small = TextStyle(fontSize = 13.sp)
    val caption = TextStyle(fontSize = 12.sp)
    val overline = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.8.sp)
    val button = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
}

private fun Context.findActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) {
        if (c is Activity) return c
        c = c.baseContext
    }
    return null
}

@Composable
fun SportCourtsTheme(dark: Boolean, content: @Composable () -> Unit) {
    val colors = if (dark) DarkColors else LightColors
    val scheme = if (dark) {
        darkColorScheme(primary = colors.primary, onPrimary = colors.onPrimary, background = colors.background,
            surface = colors.background, onBackground = colors.text, onSurface = colors.text)
    } else {
        lightColorScheme(primary = colors.primary, onPrimary = colors.onPrimary, background = colors.background,
            surface = colors.background, onBackground = colors.text, onSurface = colors.text)
    }
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = view.context.findActivity()?.window
            if (window != null) {
                val controller = WindowCompat.getInsetsController(window, view)
                // тёмные значки на светлой теме и наоборот: реальная строка состояния Android остаётся читаемой
                controller.isAppearanceLightStatusBars = !dark
                controller.isAppearanceLightNavigationBars = !dark
            }
        }
    }
    CompositionLocalProvider(LocalColors provides colors) {
        MaterialTheme(colorScheme = scheme) {
            Box(Modifier.fillMaxSize().background(colors.background)) { content() }
        }
    }
}

val colors: AppColors
    @Composable get() = LocalColors.current
