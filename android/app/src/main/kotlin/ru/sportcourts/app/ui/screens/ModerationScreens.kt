package ru.sportcourts.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.Session
import ru.sportcourts.app.data.AdminReport
import ru.sportcourts.app.data.Proposal
import ru.sportcourts.app.data.RejectBody
import ru.sportcourts.app.data.ResolveBody
import ru.sportcourts.app.data.Submission
import ru.sportcourts.app.ui.LoadView
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.Loader
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.Screen
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.TabBar
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.TextInputDialog
import ru.sportcourts.app.ui.formatDateTime
import ru.sportcourts.app.ui.rememberLoader
import ru.sportcourts.app.ui.shownName
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors
import ru.sportcourts.app.ui.venueTypeName

private fun reportReasonName(r: String) = when (r) {
    "spam" -> "Спам"
    "harassment" -> "Оскорбления или домогательства"
    "inappropriate" -> "Неприемлемое содержимое"
    "fake_info" -> "Недостоверная информация"
    else -> "Другое"
}

@Composable
fun ModerationScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val session by container.session.collectAsState()
    val me = (session as? Session.In)?.me ?: return
    val tabs = buildList {
        add("Площадки"); add("Изменения"); add("История")
        if (me.canSeeReports) add("Жалобы")
    }
    var tab by remember { mutableStateOf(0) }
    val subs = rememberLoader { container.repo.call { it.modSubmissions("pending") } }
    val props = rememberLoader { container.repo.call { it.modProposals("pending") } }
    val history = rememberLoader { container.repo.call { it.decisions() } }
    val reports = rememberLoader { container.repo.call { it.adminReports("open") } }

    Screen("Модерация", onMenu = { shell.openDrawer() }) {
        Column(Modifier.fillMaxSize()) {
            TabBar(
                tabs, tab, { tab = it },
                badges = listOf(subs.value?.items?.size ?: 0, props.value?.items?.size ?: 0, 0, reports.value?.items?.size ?: 0),
            )
            when (tab) {
                0 -> LoadView(subs, Modifier.fillMaxSize()) { resp ->
                    if (resp.items.isEmpty()) EmptyState("Очередь пуста", "Новых заявок на площадки нет.")
                    else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(resp.items, key = { it.id }) { s -> SubmissionReview(s, subs, history) }
                    }
                }
                1 -> LoadView(props, Modifier.fillMaxSize()) { resp ->
                    if (resp.items.isEmpty()) EmptyState("Очередь пуста", "Предложений по изменению площадок нет.")
                    else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(resp.items, key = { it.id }) { p -> ProposalReview(p, props, history) }
                    }
                }
                2 -> LoadView(history, Modifier.fillMaxSize()) { resp ->
                    if (resp.items.isEmpty()) EmptyState("История пуста", "Здесь будут решения модераторов.")
                    else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(resp.items, key = { it.id }) { d ->
                            AppCard {
                                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(d.venueName ?: "Площадка", style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f))
                                        Tag(if (d.decision == "approved") "Одобрено" else "Отклонено")
                                    }
                                    Text(if (d.kind == "submission") "Новая площадка" else "Изменение площадки", style = AppType.caption, color = colors.textSecondary)
                                    if (!d.reason.isNullOrBlank()) Text("Причина: ${d.reason}", style = AppType.small, color = colors.text)
                                    Text("${d.moderator.shownName()} · ${formatDateTime(d.createdAt)}", style = AppType.caption, color = colors.textSecondary)
                                }
                            }
                        }
                    }
                }
                else -> ReportsList(reports)
            }
        }
    }
}

@Composable
private fun SubmissionReview(s: Submission, list: Loader<ru.sportcourts.app.data.SubmissionsResponse>, history: Loader<ru.sportcourts.app.data.DecisionsResponse>) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var reject by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    AppCard {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(s.name, style = AppType.bodyBold, color = colors.text)
            Text(s.address, style = AppType.small, color = colors.textSecondary)
            Text("Тип: ${venueTypeName(s.venueType)} · ${s.sports.joinToString { it.name }.ifEmpty { "виды спорта не указаны" }}", style = AppType.small, color = colors.text)
            Text("Координаты: %.5f, %.5f".format(java.util.Locale.US, s.latitude, s.longitude), style = AppType.caption, color = colors.textSecondary)
            s.workHours?.let { Text("Время работы: $it", style = AppType.small, color = colors.text) }
            s.costInfo?.let { Text("Стоимость: $it", style = AppType.small, color = colors.text) }
            s.description?.let { Text(it, style = AppType.small, color = colors.text) }
            if (s.photoUrl != null) {
                AsyncImage(model = container.repo.mediaUrl(s.photoUrl), contentDescription = "Фото", contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(10.dp)).background(colors.surface))
            }
            if (s.duplicates.isNotEmpty()) {
                Text("Возможные дубликаты:", style = AppType.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = colors.danger)
                s.duplicates.forEach { Text("• ${it.name} — ${it.address} (${it.distanceM} м)", style = AppType.small, color = colors.danger) }
            }
            Text("От: ${s.submitter.shownName()} · ${formatDateTime(s.createdAt)}", style = AppType.caption, color = colors.textSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    PrimaryButton("Одобрить", {
                        busy = true
                        scope.launch {
                            val r = container.repo.call { it.approveSubmission(s.id) }
                            busy = false
                            if (r is ApiResult.Fail) toaster.show(r.error.message) else toaster.show("Площадка одобрена")
                            list.load(silent = true); history.load(silent = true)
                        }
                    }, loading = busy)
                }
                Column(Modifier.weight(1f)) { SecondaryButton("Отклонить", { reject = true }, danger = true) }
            }
        }
    }
    if (reject) TextInputDialog("Причина отказа", "Что нужно исправить?", "Отклонить", onConfirm = { reason ->
        reject = false
        scope.launch {
            val r = container.repo.call { it.rejectSubmission(s.id, RejectBody(reason)) }
            if (r is ApiResult.Fail) toaster.show(r.error.message) else toaster.show("Заявка отклонена")
            list.load(silent = true); history.load(silent = true)
        }
    }, onDismiss = { reject = false }, maxLength = 500)
}

private fun diffLines(p: Proposal): List<String> {
    val c = p.current
    val out = mutableListOf<String>()
    if (p.name != c.name) out += "Название: «${c.name}» → «${p.name}»"
    if (p.address != c.address) out += "Адрес: «${c.address}» → «${p.address}»"
    if (p.latitude != c.latitude || p.longitude != c.longitude) out += "Координаты: %.5f, %.5f → %.5f, %.5f".format(java.util.Locale.US, c.latitude, c.longitude, p.latitude, p.longitude)
    if (p.venueType != c.venueType) out += "Тип: ${venueTypeName(c.venueType)} → ${venueTypeName(p.venueType)}"
    if ((p.workHours ?: "") != (c.workHours ?: "")) out += "Время работы: «${c.workHours ?: "—"}» → «${p.workHours ?: "—"}»"
    if ((p.costInfo ?: "") != (c.costInfo ?: "")) out += "Стоимость: «${c.costInfo ?: "—"}» → «${p.costInfo ?: "—"}»"
    if ((p.description ?: "") != (c.description ?: "")) out += "Описание: «${c.description ?: "—"}» → «${p.description ?: "—"}»"
    val oldSports = c.sports.map { it.name }.sorted()
    val newSports = p.sports.map { it.name }.sorted()
    if (oldSports != newSports) out += "Виды спорта: ${oldSports.joinToString().ifEmpty { "—" }} → ${newSports.joinToString().ifEmpty { "—" }}"
    if (p.photoUrl != null && p.photoUrl != c.photoUrl) out += "Новая фотография"
    return out
}

@Composable
private fun ProposalReview(p: Proposal, list: Loader<ru.sportcourts.app.data.ProposalsResponse>, history: Loader<ru.sportcourts.app.data.DecisionsResponse>) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var reject by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val lines = diffLines(p)
    AppCard {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(p.current.name.ifEmpty { p.name }, style = AppType.bodyBold, color = colors.text)
            Text("Что меняется:", style = AppType.caption, color = colors.textSecondary)
            if (lines.isEmpty()) Text("Значимых отличий не найдено.", style = AppType.small, color = colors.text)
            lines.forEach { Text("• $it", style = AppType.small, color = colors.text) }
            if (p.photoUrl != null && p.photoUrl != p.current.photoUrl) {
                AsyncImage(model = container.repo.mediaUrl(p.photoUrl), contentDescription = "Новое фото", contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(10.dp)).background(colors.surface))
            }
            Text("От: ${p.proposer.shownName()} · ${formatDateTime(p.createdAt)}", style = AppType.caption, color = colors.textSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    PrimaryButton("Одобрить", {
                        busy = true
                        scope.launch {
                            val r = container.repo.call { it.approveProposal(p.id) }
                            busy = false
                            if (r is ApiResult.Fail) toaster.show(r.error.message) else toaster.show("Изменения применены")
                            list.load(silent = true); history.load(silent = true)
                        }
                    }, loading = busy)
                }
                Column(Modifier.weight(1f)) { SecondaryButton("Отклонить", { reject = true }, danger = true) }
            }
        }
    }
    if (reject) TextInputDialog("Причина отказа", "Почему изменения не подходят?", "Отклонить", onConfirm = { reason ->
        reject = false
        scope.launch {
            val r = container.repo.call { it.rejectProposal(p.id, RejectBody(reason)) }
            if (r is ApiResult.Fail) toaster.show(r.error.message) else toaster.show("Предложение отклонено")
            list.load(silent = true); history.load(silent = true)
        }
    }, onDismiss = { reject = false }, maxLength = 500)
}

@Composable
private fun ReportsList(loader: Loader<ru.sportcourts.app.data.AdminReportsResponse>) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var resolving by remember { mutableStateOf<Pair<AdminReport, String>?>(null) }
    LoadView(loader, Modifier.fillMaxSize()) { resp ->
        if (resp.items.isEmpty()) EmptyState("Жалоб нет", "Открытых жалоб нет.")
        else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(resp.items, key = { it.id }) { r ->
                AppCard {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(reportReasonName(r.reason), style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f))
                            Text(formatDateTime(r.createdAt), style = AppType.caption, color = colors.textSecondary)
                        }
                        val target = when {
                            r.targetUser != null -> "Пользователь: ${r.targetUser.displayName.ifEmpty { r.targetUser.login }} (@${r.targetUser.login})"
                            r.targetVenueName != null -> "Площадка: ${r.targetVenueName}"
                            r.targetGameTitle != null -> "Игра: ${r.targetGameTitle}"
                            else -> "Объект удалён"
                        }
                        Text(target, style = AppType.small, color = colors.text)
                        if (!r.description.isNullOrBlank()) Text(r.description, style = AppType.small, color = colors.textSecondary)
                        Text("От: ${r.reporter.displayName.ifEmpty { r.reporter.login }}", style = AppType.caption, color = colors.textSecondary)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Column(Modifier.weight(1f)) { PrimaryButton("Решено", { resolving = r to "resolved" }) }
                            Column(Modifier.weight(1f)) { SecondaryButton("Отклонить", { resolving = r to "dismissed" }) }
                        }
                    }
                }
            }
        }
    }
    resolving?.let { (report, status) ->
        TextInputDialog(
            if (status == "resolved") "Жалоба решена" else "Отклонить жалобу", "Заметка (необязательно)", "Подтвердить",
            onConfirm = { note ->
                resolving = null
                scope.launch {
                    val res = container.repo.call { it.resolveReport(report.id, ResolveBody(status, note.ifBlank { null })) }
                    if (res is ApiResult.Fail) toaster.show(res.error.message)
                    loader.load(silent = true)
                }
            }, onDismiss = { resolving = null }, required = false,
        )
    }
}
