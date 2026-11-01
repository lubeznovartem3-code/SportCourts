package ru.sportcourts.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.Session
import ru.sportcourts.app.data.AdminUser
import ru.sportcourts.app.data.ActiveBody
import ru.sportcourts.app.data.ArchiveBody
import ru.sportcourts.app.data.RejectBody
import ru.sportcourts.app.data.ReviewFlagBody
import ru.sportcourts.app.data.RoleBody
import ru.sportcourts.app.data.SportBody
import ru.sportcourts.app.data.SportPatchBody
import ru.sportcourts.app.ui.LoadView
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.AppDialog
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.ConfirmDialog
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.KeyValue
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.Screen
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.SwitchRow
import ru.sportcourts.app.ui.components.TabBar
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.TextInputDialog
import ru.sportcourts.app.ui.formatDateTime
import ru.sportcourts.app.ui.rememberLoader
import ru.sportcourts.app.ui.shownName
import ru.sportcourts.app.ui.roleName
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors

@Composable
fun AdminScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val session by container.session.collectAsState()
    if ((session as? Session.In)?.me?.isAdmin != true) return
    var tab by remember { mutableStateOf(0) }
    val tabs = listOf("Пользователи", "Заявки на роль", "Площадки", "Виды спорта", "Система", "Журнал")
    val modRequests = rememberLoader { container.repo.call { it.adminModeratorRequests("pending") } }
    Screen("Администрирование", onMenu = { shell.openDrawer() }) {
        Column(Modifier.fillMaxSize()) {
            TabBar(tabs, tab, { tab = it }, badges = listOf(0, modRequests.value?.items?.size ?: 0))
            when (tab) {
                0 -> UsersTab()
                1 -> ModeratorRequestsTab(modRequests)
                2 -> VenuesTab()
                3 -> SportsTab()
                4 -> SystemTab()
                else -> AuditTab()
            }
        }
    }
}

// ------------------------------------------------------------------ пользователи
@Composable
private fun UsersTab() {
    val container = LocalContainer.current
    var query by remember { mutableStateOf("") }
    var applied by remember { mutableStateOf("") }
    LaunchedEffect(query) { delay(350); applied = query.trim() }
    val loader = rememberLoader(applied) { container.repo.call { it.adminUsers(applied.ifEmpty { null }) } }
    var selected by remember { mutableStateOf<AdminUser?>(null) }
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.padding(16.dp)) { AppTextField(query, { query = it }, placeholder = "Поиск по логину или имени", maxLength = 64) }
        LoadView(loader, Modifier.fillMaxSize()) { resp ->
            if (resp.items.isEmpty()) EmptyState("Никого не найдено", "Измените запрос.")
            else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(resp.items, key = { it.id }) { u ->
                    AppCard(onClick = { selected = u }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(u.displayName, style = AppType.bodyBold, color = colors.text, maxLines = 1)
                                Text("@${u.login} · ${roleName(u.role)}", style = AppType.caption, color = colors.textSecondary)
                            }
                            if (!u.isActive) Tag("Отключён")
                        }
                    }
                }
            }
        }
    }
    selected?.let { u -> UserActionsDialog(u, onDismiss = { selected = null }, onChanged = { loader.load(silent = true) }) }
}

@Composable
private fun UserActionsDialog(user: AdminUser, onDismiss: () -> Unit, onChanged: () -> Unit) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var tempPassword by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmReset by remember { mutableStateOf(false) }
    var current by remember { mutableStateOf(user) }
    val isAdminUser = current.role == "admin"

    fun perform(block: suspend () -> ApiResult<*>, after: () -> Unit = {}) {
        error = null
        scope.launch {
            when (val r = block()) {
                is ApiResult.Ok -> { after(); onChanged() }
                is ApiResult.Fail -> error = r.error.message
            }
        }
    }

    AppDialog(onDismiss, current.displayName, content = {
        Text("@${current.login} · ${roleName(current.role)} · с ${formatDateTime(current.createdAt)}", style = AppType.small, color = colors.textSecondary)
        if (isAdminUser) {
            Text("Права администратора и его пароль меняются только командой на сервере.", style = AppType.small, color = colors.textSecondary)
        } else {
            SwitchRow("Модератор", current.role == "moderator", { on ->
                perform({ container.repo.call { it.setRole(current.id, RoleBody(if (on) "moderator" else "user")) } }) {
                    current = current.copy(role = if (on) "moderator" else "user", canReviewReports = if (on) current.canReviewReports else false)
                }
            })
            if (current.role == "moderator") {
                SwitchRow("Может разбирать жалобы", current.canReviewReports, { on ->
                    perform({ container.repo.call { it.setReviewFlag(current.id, ReviewFlagBody(on)) } }) { current = current.copy(canReviewReports = on) }
                })
            }
            SwitchRow("Аккаунт активен", current.isActive, { on ->
                perform({ container.repo.call { it.setActive(current.id, ActiveBody(on)) } }) { current = current.copy(isActive = on) }
            }, hint = "Отключённый пользователь не может войти")
            SecondaryButton("Сбросить пароль", { confirmReset = true })
        }
        InlineError(error)
        tempPassword?.let {
            Text("Временный пароль (показывается один раз):", style = AppType.small, color = colors.textSecondary)
            Text(it, style = AppType.title, color = colors.text)
            Text("Передайте его пользователю. При входе приложение попросит задать новый пароль.", style = AppType.caption, color = colors.textSecondary)
        }
    }) { SecondaryButton("Закрыть", onDismiss) }

    if (confirmReset) ConfirmDialog("Сбросить пароль?", "Все сессии пользователя завершатся, будет выдан временный пароль.", "Сбросить", {
        confirmReset = false
        scope.launch {
            when (val r = container.repo.call { it.resetPassword(current.id) }) {
                is ApiResult.Ok -> { tempPassword = r.value.temporaryPassword; onChanged() }
                is ApiResult.Fail -> error = r.error.message
            }
        }
    }, { confirmReset = false }, danger = true)
}

// ------------------------------------------------------------------ заявки на роль
@Composable
private fun ModeratorRequestsTab(loader: ru.sportcourts.app.ui.Loader<ru.sportcourts.app.data.ModeratorRequestsResponse>) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var rejecting by remember { mutableStateOf<ru.sportcourts.app.data.ModeratorRequest?>(null) }
    LoadView(loader, Modifier.fillMaxSize()) { resp ->
        if (resp.items.isEmpty()) EmptyState("Заявок нет", "Новых заявок на роль модератора нет.")
        else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(resp.items, key = { it.id }) { r ->
                AppCard {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(r.user.shownName(), style = AppType.bodyBold, color = colors.text)
                        Text("@${r.user?.login ?: ""} · ${formatDateTime(r.createdAt)}", style = AppType.caption, color = colors.textSecondary)
                        if (!r.message.isNullOrBlank()) Text(r.message, style = AppType.small, color = colors.text)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Column(Modifier.weight(1f)) {
                                PrimaryButton("Назначить", {
                                    scope.launch {
                                        val res = container.repo.call { it.approveModerator(r.id) }
                                        if (res is ApiResult.Fail) toaster.show(res.error.message) else toaster.show("Пользователь назначен модератором")
                                        loader.load(silent = true)
                                    }
                                })
                            }
                            Column(Modifier.weight(1f)) { SecondaryButton("Отклонить", { rejecting = r }, danger = true) }
                        }
                    }
                }
            }
        }
    }
    rejecting?.let { r ->
        TextInputDialog("Отклонить заявку", "Причина (увидит пользователь)", "Отклонить", onConfirm = { reason ->
            rejecting = null
            scope.launch {
                val res = container.repo.call { it.rejectModerator(r.id, RejectBody(reason)) }
                if (res is ApiResult.Fail) toaster.show(res.error.message)
                loader.load(silent = true)
            }
        }, onDismiss = { rejecting = null })
    }
}

// ------------------------------------------------------------------ площадки
@Composable
private fun VenuesTab() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader { container.repo.call { it.venues(sort = "name", limit = 200) } }
    var archiving by remember { mutableStateOf<ru.sportcourts.app.data.Venue?>(null) }
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.padding(16.dp)) { PrimaryButton("Добавить площадку", { shell.navigate("venue/new") }) }
        LoadView(loader, Modifier.fillMaxSize()) { resp ->
            if (resp.items.isEmpty()) EmptyState("Площадок нет", "Добавьте первую площадку.")
            else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(resp.items, key = { it.id }) { v ->
                    AppCard {
                        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(v.name, style = AppType.bodyBold, color = colors.text)
                            Text(v.address, style = AppType.small, color = colors.textSecondary)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Column(Modifier.weight(1f)) { SecondaryButton("Изменить", { shell.navigate("venue/edit/${v.id}") }) }
                                Column(Modifier.weight(1f)) { SecondaryButton("В архив", { archiving = v }, danger = true) }
                            }
                        }
                    }
                }
            }
        }
    }
    archiving?.let { v ->
        ConfirmDialog("Убрать в архив?", "«${v.name}» пропадёт с карты и из поиска; открытые игры на ней отменятся. Вернуть можно запросом PUT /admin/venues/${v.id}/archive с archived=false.", "В архив", {
            archiving = null
            scope.launch {
                val r = container.repo.call { it.adminArchiveVenue(v.id, ArchiveBody(true)) }
                if (r is ApiResult.Fail) toaster.show(r.error.message) else toaster.show("Площадка в архиве")
                loader.load(silent = true)
            }
        }, { archiving = null }, danger = true)
    }
}

// ------------------------------------------------------------------ виды спорта
@Composable
private fun SportsTab() {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    val loader = rememberLoader { container.repo.call { it.adminSports() } }
    var adding by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf<ru.sportcourts.app.data.Sport?>(null) }
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.padding(16.dp)) { PrimaryButton("Добавить вид спорта", { adding = true }) }
        LoadView(loader, Modifier.fillMaxSize()) { resp ->
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(resp.items, key = { it.id }) { s ->
                    AppCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(s.name, style = AppType.body, color = if (s.isActive) colors.text else colors.textSecondary, modifier = Modifier.weight(1f))
                            Box(Modifier.width(120.dp)) { SecondaryButton("Переименовать", { renaming = s }) }
                            Box(Modifier.width(8.dp)) {}
                            Box(Modifier.width(110.dp)) {
                                SecondaryButton(if (s.isActive) "Скрыть" else "Показать", {
                                    scope.launch {
                                        val r = container.repo.call { it.adminPatchSport(s.id.toLong(), SportPatchBody(isActive = !s.isActive)) }
                                        if (r is ApiResult.Fail) toaster.show(r.error.message)
                                        loader.load(silent = true)
                                    }
                                })
                            }
                        }
                    }
                }
            }
        }
    }
    if (adding) TextInputDialog("Новый вид спорта", "Название", "Добавить", onConfirm = { name ->
        adding = false
        scope.launch {
            val r = container.repo.call { it.adminAddSport(SportBody(name)) }
            if (r is ApiResult.Fail) toaster.show(r.error.message)
            loader.load(silent = true)
        }
    }, onDismiss = { adding = false }, multiline = false, maxLength = 40)
    renaming?.let { s ->
        TextInputDialog("Переименовать", "Новое название", "Сохранить", onConfirm = { name ->
            renaming = null
            scope.launch {
                val r = container.repo.call { it.adminPatchSport(s.id.toLong(), SportPatchBody(name = name)) }
                if (r is ApiResult.Fail) toaster.show(r.error.message)
                loader.load(silent = true)
            }
        }, onDismiss = { renaming = null }, multiline = false, maxLength = 40)
    }
}

// ------------------------------------------------------------------ система и журнал
@Composable
private fun SystemTab() {
    val container = LocalContainer.current
    val loader = rememberLoader { container.repo.call { it.system() } }
    LoadView(loader, Modifier.fillMaxSize()) { s ->
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            AppCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Диск сервера", style = AppType.bodyBold, color = colors.text)
                    Row(Modifier.fillMaxWidth()) {
                        KeyValue("Свободно", "%.1f ГБ".format(java.util.Locale("ru"), s.disk.freeGb), Modifier.weight(1f))
                        KeyValue("Всего", "%.1f ГБ".format(java.util.Locale("ru"), s.disk.totalGb), Modifier.weight(1f))
                    }
                }
            }
            if (s.warnings.isNotEmpty()) {
                AppCard {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Предупреждения", style = AppType.bodyBold, color = colors.danger)
                        s.warnings.forEach { Text("• $it", style = AppType.small, color = colors.danger) }
                    }
                }
            }
            AppCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("В базе", style = AppType.bodyBold, color = colors.text)
                    Row(Modifier.fillMaxWidth()) {
                        KeyValue("Пользователей", s.counts.users.toString(), Modifier.weight(1f))
                        KeyValue("Площадок", s.counts.venues.toString(), Modifier.weight(1f))
                    }
                    Row(Modifier.fillMaxWidth()) {
                        KeyValue("Заявок на площадки", s.counts.pendingSubmissions.toString(), Modifier.weight(1f))
                        KeyValue("Предложений правок", s.counts.pendingProposals.toString(), Modifier.weight(1f))
                    }
                    Row(Modifier.fillMaxWidth()) {
                        KeyValue("Открытых жалоб", s.counts.openReports.toString(), Modifier.weight(1f))
                        KeyValue("Заявок на роль", s.counts.pendingModeratorRequests.toString(), Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun AuditTab() {
    val container = LocalContainer.current
    val loader = rememberLoader { container.repo.call { it.audit() } }
    LoadView(loader, Modifier.fillMaxSize()) { resp ->
        if (resp.items.isEmpty()) EmptyState("Журнал пуст", "Действия модераторов и администраторов появятся здесь.")
        else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(resp.items, key = { it.id }) { e ->
                AppCard {
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text(e.action, style = AppType.bodyBold, color = colors.text)
                        Text("${e.actorLogin ?: "система"} · ${formatDateTime(e.createdAt)}" + if (e.targetType != null) " · ${e.targetType} #${e.targetId}" else "", style = AppType.caption, color = colors.textSecondary)
                        if (!e.details.isNullOrBlank()) Text(e.details, style = AppType.small, color = colors.textSecondary)
                    }
                }
            }
        }
    }
}
