package ru.sportcourts.app.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Done
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ru.sportcourts.app.BuildConfig
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.Session
import ru.sportcourts.app.data.ChangeLoginBody
import ru.sportcourts.app.data.ChangePasswordBody
import ru.sportcourts.app.data.DeleteAccountBody
import ru.sportcourts.app.data.ModeratorRequestBody
import ru.sportcourts.app.data.ProfileBody
import ru.sportcourts.app.ui.LoadView
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.Validation
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.AppDialog
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.Avatar
import ru.sportcourts.app.ui.components.Chip
import ru.sportcourts.app.ui.components.ChipFlow
import ru.sportcourts.app.ui.components.ConfirmDialog
import ru.sportcourts.app.ui.components.Divider
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.FormColumn
import ru.sportcourts.app.ui.components.IconAction
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.Screen
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.SectionHeader
import ru.sportcourts.app.ui.components.SwitchRow
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.TextInputDialog
import ru.sportcourts.app.ui.components.TextLink
import ru.sportcourts.app.ui.formatDateTime
import ru.sportcourts.app.ui.readImageForUpload
import ru.sportcourts.app.ui.jpegPart
import ru.sportcourts.app.ui.rememberLoader
import ru.sportcourts.app.ui.roleName
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors

// ------------------------------------------------------------------ мой профиль
@Composable
fun ProfileScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val session by container.session.collectAsState()
    val me = (session as? Session.In)?.me ?: return
    val sports = rememberLoader { container.repo.call { it.sports() } }
    var name by remember(me.id) { mutableStateOf(me.displayName) }
    var chosen by remember(me.id) { mutableStateOf(me.favoriteSports.map { it.id }.toSet()) }
    var busy by remember { mutableStateOf(false) }
    var photoBusy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            photoBusy = true
            scope.launch {
                val bytes = readImageForUpload(context, uri, 1024)
                if (bytes == null) {
                    photoBusy = false
                    toaster.show("Не удалось прочитать изображение")
                } else {
                    val r = container.repo.call { it.setAvatar(jpegPart(bytes, "avatar.jpg")) }
                    photoBusy = false
                    when (r) {
                        is ApiResult.Ok -> { container.updateMe(r.value); toaster.show("Фото обновлено") }
                        is ApiResult.Fail -> toaster.show(r.error.message)
                    }
                }
            }
        }
    }

    Screen("Профиль", onBack = { shell.back() }) {
        FormColumn {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Avatar(container.repo.mediaUrl(me.avatarUrl), me.displayName, 104.dp)
                TextLink(if (photoBusy) "Загрузка…" else "Изменить фото профиля", { if (!photoBusy) picker.launch("image/*") }, color = colors.text)
                if (me.avatarUrl != null) TextLink("Удалить фото", {
                    scope.launch {
                        val r = container.repo.call { it.deleteAvatar() }
                        when (r) {
                            is ApiResult.Ok -> container.updateMe(r.value)
                            is ApiResult.Fail -> toaster.show(r.error.message)
                        }
                    }
                })
                Text("@${me.login} · ${roleName(me.role)}", style = AppType.caption, color = colors.textSecondary)
            }
            AppTextField(name, { name = it }, label = "Отображаемое имя", maxLength = 64)
            Text("Любимый спорт", style = AppType.caption, color = colors.text)
            LoadView(sports, Modifier.fillMaxWidth()) { resp ->
                ChipFlow {
                    resp.items.filter { it.isActive || it.id in chosen }.forEach { s ->
                        Chip(s.name, s.id in chosen, { chosen = if (s.id in chosen) chosen - s.id else chosen + s.id })
                    }
                }
            }
            InlineError(error)
            PrimaryButton("Сохранить", {
                error = Validation.displayName(name)
                if (error == null) {
                    busy = true
                    scope.launch {
                        val r = container.repo.call { it.updateProfile(ProfileBody(name.trim(), chosen.toList())) }
                        busy = false
                        when (r) {
                            is ApiResult.Ok -> { container.updateMe(r.value); toaster.show("Профиль сохранён") }
                            is ApiResult.Fail -> error = r.error.message
                        }
                    }
                }
            }, loading = busy)
        }
    }
}

// ------------------------------------------------------------------ настройки
@Composable
fun SettingsScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val session by container.session.collectAsState()
    val settings by container.settings.collectAsState()
    val me = (session as? Session.In)?.me ?: return
    val dark = colors.dark

    var currentPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var newLogin by remember { mutableStateOf("") }
    var secError by remember { mutableStateOf<String?>(null) }
    var secBusy by remember { mutableStateOf(false) }
    var showServer by remember { mutableStateOf(false) }
    var showLogout by remember { mutableStateOf(false) }
    var showDelete by remember { mutableStateOf(false) }
    var showModerator by remember { mutableStateOf(false) }
    val modRequests = rememberLoader { container.repo.call { it.myModeratorRequests() } }

    Screen("Настройки", onBack = { shell.back() }) {
        FormColumn {
            SectionHeader("Аккаунт и безопасность")
            Text("Вы вошли как @${me.login}", style = AppType.small, color = colors.textSecondary)
            AppTextField(currentPassword, { currentPassword = it; secError = null }, label = "Текущий пароль", placeholder = "Нужен для смены пароля или логина", password = true, maxLength = 128)
            AppTextField(newPassword, { newPassword = it; secError = null }, label = "Сменить пароль", placeholder = "Новый пароль (от 8 символов)", password = true, maxLength = 128)
            AppTextField(newLogin, { newLogin = it; secError = null }, label = "Сменить логин", placeholder = "Новый логин (регистр важен)", maxLength = 32)
            InlineError(secError)
            PrimaryButton("Сохранить изменения", {
                secError = null
                val wantsPassword = newPassword.isNotEmpty()
                val wantsLogin = newLogin.isNotBlank()
                when {
                    !wantsPassword && !wantsLogin -> secError = "Введите новый пароль или новый логин"
                    currentPassword.isEmpty() -> secError = "Введите текущий пароль"
                    wantsPassword && Validation.password(newPassword) != null -> secError = Validation.password(newPassword)
                    wantsLogin && Validation.login(newLogin) != null -> secError = Validation.login(newLogin)
                    else -> {
                        secBusy = true
                        scope.launch {
                            var failure: String? = null
                            if (wantsLogin) {
                                when (val r = container.repo.call { it.changeLogin(ChangeLoginBody(currentPassword, newLogin.trim())) }) {
                                    is ApiResult.Ok -> container.updateMe(r.value)
                                    is ApiResult.Fail -> failure = r.error.message
                                }
                            }
                            if (failure == null && wantsPassword) {
                                when (val r = container.repo.call { it.changePassword(ChangePasswordBody(currentPassword, newPassword)) }) {
                                    is ApiResult.Ok -> container.updateMe(r.value)
                                    is ApiResult.Fail -> failure = r.error.message
                                }
                            }
                            secBusy = false
                            if (failure != null) secError = failure else {
                                toaster.show("Изменения сохранены")
                                currentPassword = ""; newPassword = ""; newLogin = ""
                            }
                        }
                    }
                }
            }, loading = secBusy)

            SectionHeader("Интерфейс")
            SwitchRow("Светлая тема", !dark, { on -> scope.launch { container.setTheme(if (on) "light" else "dark") } })
            Divider()
            SwitchRow("Тёмная тема", dark, { on -> scope.launch { container.setTheme(if (on) "dark" else "light") } })
            Divider()

            SectionHeader("Сервер")
            Text(settings?.apiUrl?.ifBlank { "Адрес не задан" } ?: "", style = AppType.small, color = colors.text)
            SecondaryButton("Изменить адрес сервера", { showServer = true })
            Text("Адрес меняется, если сервер или туннель перезапускали. Пересобирать приложение не нужно.", style = AppType.caption, color = colors.textSecondary)

            SectionHeader("Люди")
            SecondaryButton("Заблокированные пользователи", { shell.navigate("settings/blocks") })

            if (!me.isModerator) {
                SectionHeader("Роль модератора")
                val latest = modRequests.value?.items?.firstOrNull()
                when (latest?.status) {
                    "pending" -> Text("Ваша заявка на роль модератора рассматривается администратором.", style = AppType.small, color = colors.textSecondary)
                    else -> {
                        if (latest?.status == "rejected") Text("Прошлая заявка отклонена" + (latest.decisionReason?.let { ": $it" } ?: "") + ".", style = AppType.small, color = colors.textSecondary)
                        Text("Модераторы проверяют новые площадки и предложения по изменениям.", style = AppType.small, color = colors.textSecondary)
                        SecondaryButton("Подать заявку на роль модератора", { showModerator = true })
                    }
                }
            }

            SectionHeader("О приложении")
            Text("SportCourts ${BuildConfig.VERSION_NAME}", style = AppType.small, color = colors.textSecondary)

            Spacer(Modifier.height(8.dp))
            SecondaryButton("Выйти из аккаунта", { showLogout = true })
            SecondaryButton("Удалить аккаунт", { showDelete = true }, danger = true)
        }
    }

    if (showServer) ServerAddressDialog(onDismiss = { showServer = false })
    if (showLogout) ConfirmDialog("Выйти из аккаунта?", "Потребуется снова ввести логин и пароль.", "Выйти", { showLogout = false; container.logout() }, { showLogout = false })
    if (showDelete) DeleteAccountDialog(onDismiss = { showDelete = false })
    if (showModerator) TextInputDialog(
        "Заявка на модератора", "Расскажите, почему вы хотите помогать (необязательно)", "Отправить",
        onConfirm = { text ->
            showModerator = false
            scope.launch {
                val r = container.repo.call { it.requestModerator(ModeratorRequestBody(text.ifBlank { null })) }
                when (r) {
                    is ApiResult.Ok -> { toaster.show("Заявка отправлена"); modRequests.load(silent = true) }
                    is ApiResult.Fail -> toaster.show(r.error.message)
                }
            }
        }, onDismiss = { showModerator = false }, required = false,
    )
}

@Composable
private fun DeleteAccountDialog(onDismiss: () -> Unit) {
    val container = LocalContainer.current
    val scope = rememberCoroutineScope()
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppDialog(onDismiss, "Удалить аккаунт", content = {
        Text(
            "Аккаунт будет удалён без возможности восстановления: логин освободится, друзья, переписка и уведомления удалятся, " +
                "ваши открытые игры отменятся, а неразобранные заявки на площадки будут отозваны. " +
                "Уже одобренные площадки и история игр останутся без вашего имени. Введите пароль для подтверждения.",
            style = AppType.small, color = colors.textSecondary,
        )
        AppTextField(password, { password = it; error = null }, label = "Пароль", password = true, maxLength = 128)
        InlineError(error)
    }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton("Удалить навсегда", {
                if (password.isEmpty()) { error = "Введите пароль"; return@PrimaryButton }
                busy = true
                scope.launch {
                    val r = container.repo.call { it.deleteAccount(DeleteAccountBody(password)) }
                    busy = false
                    when (r) {
                        is ApiResult.Ok -> { container.logout(); onDismiss() }
                        is ApiResult.Fail -> error = r.error.message
                    }
                }
            }, loading = busy, danger = true)
            SecondaryButton("Отмена", onDismiss)
        }
    }
}

// ------------------------------------------------------------------ уведомления
@Composable
fun NotificationsScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader { container.repo.call { it.notifications() } }
    LaunchedEffect(loader.value) {
        loader.value?.let { container.updateUnread(container.unread.value.copy(unreadCount = it.unreadCount)) }
    }
    Screen("Уведомления", onMenu = { shell.openDrawer() }, actions = {
        if ((loader.value?.unreadCount ?: 0) > 0) IconAction(Icons.Filled.Done, "Прочитать все", {
            scope.launch {
                container.repo.call { it.readAllNotifications() }
                loader.load(silent = true)
            }
        })
    }) {
        LoadView(loader, Modifier.fillMaxSize()) { resp ->
            if (resp.items.isEmpty()) {
                EmptyState("Уведомлений нет", "Здесь появятся решения по вашим заявкам на площадки, запросы в друзья и другие события.")
            } else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(resp.items, key = { it.id }) { n ->
                    val unread = n.readAt == null
                    AppCard(onClick = {
                        scope.launch {
                            if (unread) container.repo.call { it.readNotification(n.id) }
                            loader.load(silent = true)
                        }
                        when (n.type) {
                            "friend_request", "friend_accepted" -> shell.navigate("friends")
                            "venue_submission_decided", "venue_change_decided" -> shell.navigate("submissions")
                            "moderator_request_decided" -> shell.navigate("settings")
                        }
                    }) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(n.title, style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f))
                                if (unread) Tag("Новое")
                            }
                            if (!n.body.isNullOrBlank()) Text(n.body, style = AppType.small, color = colors.textSecondary)
                            Text(formatDateTime(n.createdAt), style = AppType.caption, color = colors.textSecondary)
                        }
                    }
                }
            }
        }
    }
}
