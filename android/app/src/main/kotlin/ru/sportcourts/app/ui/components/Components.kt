package ru.sportcourts.app.ui.components

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.foundation.selection.toggleable
import coil3.compose.AsyncImage
import ru.sportcourts.app.core.ApiError
import ru.sportcourts.app.ui.initialsOf
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors

private val FieldShape = RoundedCornerShape(10.dp)
private val ButtonShape = RoundedCornerShape(10.dp)

// ------------------------------------------------------------------ кнопки
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    danger: Boolean = false,
) {
    val c = colors
    val bg = if (danger) c.danger else c.primary
    val fg = if (danger) Color.White else c.onPrimary
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(50.dp)
            .clip(ButtonShape)
            .background(if (enabled) bg else bg.copy(alpha = 0.4f))
            .clickable(enabled = enabled && !loading, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (loading) CircularProgressIndicator(Modifier.size(22.dp), color = fg, strokeWidth = 2.dp)
        else Text(text, style = AppType.button, color = fg)
    }
}

@Composable
fun SecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    danger: Boolean = false,
) {
    val c = colors
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(48.dp)
            .clip(ButtonShape)
            .border(1.dp, c.border, ButtonShape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = AppType.button, color = if (danger) c.danger else if (enabled) c.text else c.textSecondary)
    }
}

@Composable
fun TextLink(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = colors.textSecondary) {
    Text(
        text, style = AppType.small, color = color, textDecoration = TextDecoration.Underline,
        modifier = modifier.clickable(role = Role.Button, onClick = onClick).padding(vertical = 6.dp, horizontal = 4.dp),
    )
}

@Composable
fun IconAction(icon: ImageVector, description: String, onClick: () -> Unit, modifier: Modifier = Modifier, tint: Color = colors.text) {
    Box(
        modifier = modifier.size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, contentDescription = description, tint = tint, modifier = Modifier.size(22.dp)) }
}

// ------------------------------------------------------------------ поля ввода
@Composable
fun AppTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    label: String? = null,
    placeholder: String = "",
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    onImeAction: (() -> Unit)? = null,
    singleLine: Boolean = true,
    minLines: Int = 1,
    maxLength: Int = Int.MAX_VALUE,
    error: String? = null,
    enabled: Boolean = true,
) {
    val c = colors
    var visible by remember { mutableStateOf(false) }
    Column(modifier.fillMaxWidth()) {
        if (label != null) {
            Text(label, style = AppType.caption, color = c.text, modifier = Modifier.padding(bottom = 6.dp))
        }
        val borderColor = if (error != null) c.danger else c.border
        BasicTextField(
            value = value,
            onValueChange = { if (it.length <= maxLength) onValueChange(it) },
            enabled = enabled,
            singleLine = singleLine,
            minLines = minLines,
            textStyle = AppType.body.copy(color = c.text),
            cursorBrush = SolidColor(c.text),
            visualTransformation = if (password && !visible) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(
                keyboardType = if (password) KeyboardType.Password else keyboardType,
                imeAction = imeAction,
            ),
            keyboardActions = KeyboardActions(onAny = { onImeAction?.invoke() }),
            decorationBox = { inner ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(FieldShape)
                        .background(c.surface)
                        .border(1.dp, borderColor, FieldShape)
                        .padding(horizontal = 14.dp, vertical = 13.dp),
                    verticalAlignment = if (singleLine) Alignment.CenterVertically else Alignment.Top,
                ) {
                    Box(Modifier.weight(1f)) {
                        if (value.isEmpty()) Text(placeholder, style = AppType.body, color = c.textSecondary)
                        inner()
                    }
                    if (password) {
                        Text(
                            if (visible) "Скрыть" else "Показать", style = AppType.caption, color = c.textSecondary,
                            modifier = Modifier.padding(start = 8.dp).clickable(role = Role.Button) { visible = !visible },
                        )
                    }
                }
            },
        )
        if (error != null) Text(error, style = AppType.caption, color = c.danger, modifier = Modifier.padding(top = 4.dp))
    }
}

// ------------------------------------------------------------------ переключатель
@Composable
fun AppSwitch(checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier) {
    val c = colors
    val offset by animateDpAsState(if (checked) 20.dp else 2.dp, label = "thumb")
    Box(
        modifier
            .width(46.dp).height(28.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(if (checked) c.primary else c.border)
            .toggleable(value = checked, role = Role.Switch, onValueChange = onCheckedChange),
    ) {
        Box(
            Modifier.offset(x = offset, y = 2.dp).size(24.dp).clip(CircleShape)
                .background(if (checked) c.onPrimary else c.background)
        )
    }
}

@Composable
fun SwitchRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier, hint: String? = null) {
    val c = colors
    Row(
        modifier.fillMaxWidth().clickable { onCheckedChange(!checked) }.padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = AppType.body, color = c.text)
            if (hint != null) Text(hint, style = AppType.caption, color = c.textSecondary)
        }
        AppSwitch(checked, onCheckedChange)
    }
}

// ------------------------------------------------------------------ чипы и метки
@Composable
fun Chip(text: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = colors
    val shape = RoundedCornerShape(18.dp)
    Box(
        modifier
            .clip(shape)
            .background(if (selected) c.primary else c.surface)
            .border(1.dp, if (selected) c.primary else c.border, shape)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
    ) { Text(text, style = AppType.small, color = if (selected) c.onPrimary else c.text, maxLines = 1) }
}

@Composable
fun Tag(text: String, modifier: Modifier = Modifier) {
    val c = colors
    Box(modifier.clip(RoundedCornerShape(6.dp)).background(c.surface).border(1.dp, c.border, RoundedCornerShape(6.dp)).padding(horizontal = 8.dp, vertical = 3.dp)) {
        Text(text, style = AppType.caption, color = c.text, maxLines = 1)
    }
}

@Composable
fun Badge(count: Int, modifier: Modifier = Modifier) {
    if (count <= 0) return
    val c = colors
    Box(
        modifier.widthIn(min = 18.dp).height(18.dp).clip(CircleShape).background(c.danger).padding(horizontal = 6.dp, vertical = 1.dp),
        contentAlignment = Alignment.Center,
    ) { Text(if (count > 99) "99+" else count.toString(), style = AppType.caption.copy(fontWeight = FontWeight.SemiBold), color = Color.White) }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChipFlow(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { content() }
}

@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = AppType.overline, color = colors.textSecondary, modifier = modifier.padding(top = 16.dp, bottom = 8.dp))
}

@Composable
fun Divider(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(1.dp).background(colors.border))
}

@Composable
fun AppCard(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val c = colors
    val shape = RoundedCornerShape(14.dp)
    val m = modifier.fillMaxWidth().clip(shape).border(1.dp, c.border, shape).background(c.background)
    Box((if (onClick != null) m.clickable(onClick = onClick) else m).padding(14.dp)) { content() }
}

// ------------------------------------------------------------------ аватар
@Composable
fun Avatar(url: String?, name: String, size: Dp = 40.dp, online: Boolean? = null, modifier: Modifier = Modifier) {
    val c = colors
    Box(modifier.size(size)) {
        Box(Modifier.size(size).clip(CircleShape).background(c.surface).border(1.dp, c.border, CircleShape), contentAlignment = Alignment.Center) {
            Text(initialsOf(name), color = c.textSecondary, fontSize = (size.value * 0.38f).sp, fontWeight = FontWeight.SemiBold)
            if (url != null) {
                AsyncImage(model = url, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            }
        }
        if (online != null) {
            val dot = (size.value * 0.28f).coerceAtLeast(9f).dp
            Box(
                Modifier.align(Alignment.BottomEnd).size(dot).clip(CircleShape)
                    .background(if (online) c.online else c.textSecondary)
                    .border(2.dp, c.background, CircleShape)
            )
        }
    }
}

// ------------------------------------------------------------------ шапка и каркас экрана
@Composable
fun TopBar(
    title: String,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = null,
    onMenu: (() -> Unit)? = null,
    subtitle: String? = null,
    subtitleColor: Color = colors.textSecondary,
    leading: (@Composable () -> Unit)? = null,
    actions: @Composable () -> Unit = {},
) {
    val c = colors
    Column(modifier.fillMaxWidth().background(c.background).statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().height(56.dp).padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            if (onBack != null) IconAction(Icons.AutoMirrored.Filled.ArrowBack, "Назад", onBack)
            else if (onMenu != null) IconAction(Icons.Filled.Menu, "Меню", onMenu)
            else Spacer(Modifier.width(12.dp))
            if (leading != null) { leading(); Spacer(Modifier.width(8.dp)) }
            Column(Modifier.weight(1f)) {
                Text(title, style = AppType.screenTitle, color = c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (subtitle != null) Text(subtitle, style = AppType.caption, color = subtitleColor, maxLines = 1)
            }
            actions()
        }
        Divider()
    }
}

/** Экран с шапкой: сверху отступ под строку состояния, снизу под панель навигации и клавиатуру. */
@Composable
fun Screen(
    title: String,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = null,
    onMenu: (() -> Unit)? = null,
    subtitle: String? = null,
    subtitleColor: Color = colors.textSecondary,
    leading: (@Composable () -> Unit)? = null,
    actions: @Composable () -> Unit = {},
    content: @Composable () -> Unit,
) {
    Column(modifier.fillMaxSize().background(colors.background)) {
        TopBar(title, onBack = onBack, onMenu = onMenu, subtitle = subtitle, subtitleColor = subtitleColor, leading = leading, actions = actions)
        Box(Modifier.weight(1f).fillMaxWidth().navigationBarsPadding().imePadding()) { content() }
    }
}

/** Прокручиваемое содержимое формы с обычными отступами. */
@Composable
fun FormColumn(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) { content() }
}

// ------------------------------------------------------------------ состояния
@Composable
fun LoadingBox(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = colors.textSecondary, strokeWidth = 2.dp, modifier = Modifier.size(28.dp))
    }
}

@Composable
fun EmptyState(title: String, text: String, modifier: Modifier = Modifier, mark: String = "•", action: String? = null, onAction: (() -> Unit)? = null) {
    val c = colors
    Column(modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Box(Modifier.size(72.dp).clip(CircleShape).background(c.surface).border(1.dp, c.border, CircleShape), contentAlignment = Alignment.Center) {
            Text(mark, fontSize = 26.sp, color = c.textSecondary)
        }
        Spacer(Modifier.height(16.dp))
        Text(title, style = AppType.bodyBold, color = c.text, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text(text, style = AppType.small, color = c.textSecondary, textAlign = TextAlign.Center)
        if (action != null && onAction != null) {
            Spacer(Modifier.height(18.dp))
            PrimaryButton(action, onAction, Modifier.widthIn(max = 260.dp))
        }
    }
}

@Composable
fun ErrorState(error: ApiError, onRetry: (() -> Unit)?, modifier: Modifier = Modifier) {
    EmptyState(
        title = if (error.network) "Нет связи с сервером" else "Не удалось загрузить",
        text = error.message,
        mark = "!",
        action = if (onRetry != null) "Повторить" else null,
        onAction = onRetry,
        modifier = modifier,
    )
}

/** Небольшое сообщение об ошибке внутри формы. */
@Composable
fun InlineError(text: String?, modifier: Modifier = Modifier) {
    if (text == null) return
    Text(text, style = AppType.small, color = colors.danger, modifier = modifier.fillMaxWidth())
}

// ------------------------------------------------------------------ диалоги
@Composable
fun AppDialog(onDismiss: () -> Unit, title: String, content: @Composable () -> Unit, buttons: @Composable () -> Unit) {
    val c = colors
    Dialog(onDismissRequest = onDismiss) {
        Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.background)
                .border(1.dp, c.border, RoundedCornerShape(16.dp)).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(title, style = AppType.title, color = c.text)
            content()
            Spacer(Modifier.height(2.dp))
            buttons()
        }
    }
}

@Composable
fun ConfirmDialog(
    title: String,
    text: String,
    confirmText: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    danger: Boolean = false,
    dismissText: String = "Отмена",
) {
    AppDialog(onDismiss, title, content = { Text(text, style = AppType.body, color = colors.textSecondary) }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton(confirmText, onConfirm, danger = danger)
            SecondaryButton(dismissText, onDismiss)
        }
    }
}

@Composable
fun InfoDialog(title: String, text: String, onDismiss: () -> Unit, buttonText: String = "Понятно") {
    AppDialog(onDismiss, title, content = { Text(text, style = AppType.body, color = colors.textSecondary) }) {
        PrimaryButton(buttonText, onDismiss)
    }
}

@Composable
fun TextInputDialog(
    title: String,
    label: String,
    confirmText: String,
    onConfirm: (String) -> Unit,
    onDismiss: () -> Unit,
    placeholder: String = "",
    required: Boolean = true,
    multiline: Boolean = true,
    maxLength: Int = 500,
) {
    var text by remember { mutableStateOf("") }
    AppDialog(onDismiss, title, content = {
        AppTextField(text, { text = it }, label = label, placeholder = placeholder, singleLine = !multiline, minLines = if (multiline) 3 else 1, maxLength = maxLength, imeAction = ImeAction.Default)
    }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton(confirmText, { onConfirm(text.trim()) }, enabled = !required || text.isNotBlank())
            SecondaryButton("Отмена", onDismiss)
        }
    }
}

/** Выбор одного пункта из списка во всплывающем окне. */
@Composable
fun <T> PickerDialog(title: String, items: List<T>, label: (T) -> String, onPick: (T) -> Unit, onDismiss: () -> Unit) {
    val c = colors
    AppDialog(onDismiss, title, content = {
        Column(Modifier.fillMaxWidth().heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
            items.forEach { item ->
                Text(
                    label(item), style = AppType.body, color = c.text,
                    modifier = Modifier.fillMaxWidth().clickable { onPick(item) }.padding(vertical = 13.dp),
                )
                Divider()
            }
        }
    }) { SecondaryButton("Отмена", onDismiss) }
}

// ------------------------------------------------------------------ вкладки
@Composable
fun TabBar(tabs: List<String>, selected: Int, onSelect: (Int) -> Unit, badges: List<Int> = emptyList(), modifier: Modifier = Modifier) {
    val c = colors
    Column(modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            tabs.forEachIndexed { i, t ->
                Column(
                    Modifier.clickable { onSelect(i) }.padding(horizontal = 14.dp).padding(top = 12.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(t, style = AppType.small.copy(fontWeight = if (i == selected) FontWeight.SemiBold else FontWeight.Normal),
                            color = if (i == selected) c.text else c.textSecondary, maxLines = 1)
                        val b = badges.getOrElse(i) { 0 }
                        if (b > 0) { Spacer(Modifier.width(6.dp)); Badge(b) }
                    }
                    Spacer(Modifier.height(10.dp))
                    Box(Modifier.height(2.dp).widthIn(min = 20.dp).fillMaxWidth().background(if (i == selected) c.primary else Color.Transparent))
                }
            }
        }
        Divider()
    }
}

// ------------------------------------------------------------------ прочее
@Composable
fun ProgressRow(text: String) {
    Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.size(18.dp), color = colors.textSecondary, strokeWidth = 2.dp)
        Spacer(Modifier.width(10.dp))
        Text(text, style = AppType.small, color = colors.textSecondary)
    }
}

@Composable
fun KeyValue(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label.uppercase(), style = AppType.overline.copy(fontSize = 10.sp), color = colors.textSecondary)
        Spacer(Modifier.height(3.dp))
        Text(value, style = AppType.small.copy(fontWeight = FontWeight.SemiBold), color = colors.text)
    }
}
