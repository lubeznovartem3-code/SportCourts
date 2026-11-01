package ru.sportcourts.app.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.core.Session
import ru.sportcourts.app.data.Duplicate
import ru.sportcourts.app.data.Proposal
import ru.sportcourts.app.data.Submission
import ru.sportcourts.app.data.Venue
import ru.sportcourts.app.data.VenueBody
import ru.sportcourts.app.ui.Load
import ru.sportcourts.app.ui.LoadView
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalMapKitReady
import ru.sportcourts.app.ui.LocalShell
import ru.sportcourts.app.ui.LocalToaster
import ru.sportcourts.app.ui.components.AppCard
import ru.sportcourts.app.ui.components.AppDialog
import ru.sportcourts.app.ui.components.AppTextField
import ru.sportcourts.app.ui.components.Chip
import ru.sportcourts.app.ui.components.ChipFlow
import ru.sportcourts.app.ui.components.EmptyState
import ru.sportcourts.app.ui.components.FormColumn
import ru.sportcourts.app.ui.components.InlineError
import ru.sportcourts.app.ui.components.PrimaryButton
import ru.sportcourts.app.ui.components.Screen
import ru.sportcourts.app.ui.components.SecondaryButton
import ru.sportcourts.app.ui.components.TabBar
import ru.sportcourts.app.ui.components.Tag
import ru.sportcourts.app.ui.components.TextLink
import ru.sportcourts.app.ui.formatDateTime
import ru.sportcourts.app.ui.jpegPart
import ru.sportcourts.app.ui.map.CameraRequest
import ru.sportcourts.app.ui.map.GeoPoint
import ru.sportcourts.app.ui.map.YandexMap
import ru.sportcourts.app.ui.readImageForUpload
import ru.sportcourts.app.ui.rememberLoader
import ru.sportcourts.app.ui.theme.AppType
import ru.sportcourts.app.ui.theme.colors
import ru.sportcourts.app.ui.venueTypeName

/**
 * Форма площадки. Одна и та же для четырёх случаев:
 *  - обычный пользователь/модератор, новая площадка → заявка на модерацию;
 *  - обычный пользователь/модератор, существующая → предложение изменений;
 *  - администратор, новая → площадка создаётся сразу;
 *  - администратор, существующая → изменения применяются сразу.
 */
@Composable
fun VenueFormScreen(editVenueId: Long?) {
    val container = LocalContainer.current
    val shell = LocalShell.current
    val toaster = LocalToaster.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val isAdmin = (container.session.value as? Session.In)?.me?.isAdmin == true
    val sports = rememberLoader { container.repo.call { it.sports() } }
    val existing = rememberLoader<Venue?>(editVenueId) {
        if (editVenueId != null) container.repo.call<Venue?> { it.venue(editVenueId) } else ApiResult.Ok(null)
    }

    val title = when {
        editVenueId == null && isAdmin -> "Новая площадка"
        editVenueId == null -> "Предложить площадку"
        isAdmin -> "Изменить площадку"
        else -> "Предложить изменения"
    }

    Screen(title, onBack = { shell.back() }) {
        LoadView(existing, Modifier.fillMaxSize()) { venue ->
            VenueFormBody(venue, editVenueId, isAdmin, sports.value?.items?.filter { it.isActive }.orEmpty(), onDone = { message ->
                toaster.show(message)
                shell.back()
            })
        }
    }
}

@Composable
private fun VenueFormBody(
    venue: Venue?,
    editVenueId: Long?,
    isAdmin: Boolean,
    sports: List<ru.sportcourts.app.data.Sport>,
    onDone: (String) -> Unit,
) {
    val container = LocalContainer.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val mapKitReady = LocalMapKitReady.current

    var name by remember { mutableStateOf(venue?.name ?: "") }
    var address by remember { mutableStateOf(venue?.address ?: "") }
    var latText by remember { mutableStateOf(venue?.latitude?.toString() ?: "") }
    var lonText by remember { mutableStateOf(venue?.longitude?.toString() ?: "") }
    var type by remember { mutableStateOf(venue?.venueType ?: "outdoor") }
    var chosen by remember { mutableStateOf(venue?.sports?.map { it.id }?.toSet() ?: emptySet()) }
    var description by remember { mutableStateOf(venue?.description ?: "") }
    var hours by remember { mutableStateOf(venue?.workHours ?: "") }
    var cost by remember { mutableStateOf(venue?.costInfo ?: "") }
    var photoToken by remember { mutableStateOf<String?>(null) }
    var photoUri by remember { mutableStateOf<Uri?>(null) }
    var photoBusy by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var showPicker by remember { mutableStateOf(false) }
    var duplicates by remember { mutableStateOf<List<Duplicate>?>(null) }

    val photoLauncher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            photoBusy = true
            error = null
            scope.launch {
                val bytes = readImageForUpload(context, uri)
                if (bytes == null) {
                    photoBusy = false
                    error = "Не удалось прочитать изображение"
                } else {
                    val r = container.repo.call { it.uploadVenuePhoto(jpegPart(bytes)) }
                    photoBusy = false
                    when (r) {
                        is ApiResult.Ok -> { photoToken = r.value.token; photoUri = uri }
                        is ApiResult.Fail -> error = r.error.message
                    }
                }
            }
        }
    }

    fun buildBody(force: Boolean): VenueBody? {
        val lat = latText.trim().replace(',', '.').toDoubleOrNull()
        val lon = lonText.trim().replace(',', '.').toDoubleOrNull()
        error = when {
            name.isBlank() -> "Введите название"
            address.isBlank() -> "Введите адрес"
            lat == null || lon == null || lat !in -90.0..90.0 || lon !in -180.0..180.0 ->
                "Укажите координаты: выберите точку на карте или введите широту и долготу, например 55.7558 и 37.6173"
            chosen.isEmpty() -> "Выберите хотя бы один вид спорта"
            else -> null
        }
        if (error != null || lat == null || lon == null) return null
        return VenueBody(
            name = name.trim(), address = address.trim(), latitude = lat, longitude = lon, venueType = type, sportIds = chosen.toList(),
            description = description.trim().ifEmpty { null }, workHours = hours.trim().ifEmpty { null }, costInfo = cost.trim().ifEmpty { null },
            photoToken = photoToken, force = force,
        )
    }

    fun submit(force: Boolean) {
        val body = buildBody(force) ?: return
        busy = true
        scope.launch {
            // Сначала проверяем, нет ли такой же площадки рядом (для новых площадок)
            if (editVenueId == null && !force) {
                val dup = container.repo.call { it.checkDuplicates(body) }
                if (dup is ApiResult.Ok && dup.value.duplicates.isNotEmpty()) {
                    busy = false
                    duplicates = dup.value.duplicates
                    return@launch
                }
            }
            val result: ApiResult<String> = when {
                editVenueId == null && isAdmin -> container.repo.call { it.adminCreateVenue(body) }.map { "Площадка добавлена" }
                editVenueId == null -> container.repo.call { it.submitVenue(body) }.map { "Заявка отправлена на проверку модератору" }
                isAdmin -> container.repo.call { it.adminUpdateVenue(editVenueId, body) }.map { "Изменения сохранены" }
                else -> container.repo.call { it.proposeChange(editVenueId, body) }.map { "Предложение отправлено на проверку модератору" }
            }
            busy = false
            when (result) {
                is ApiResult.Ok -> onDone(result.value)
                is ApiResult.Fail -> error = result.error.message
            }
        }
    }

    FormColumn {
        if (!isAdmin) {
            Text(
                if (editVenueId == null) "Заявку проверит модератор. После одобрения площадка появится на карте, а вы получите уведомление."
                else "Изменения применятся после проверки модератором. Пока она идёт, на карте остаются прежние данные.",
                style = AppType.small, color = colors.textSecondary,
            )
        }
        AppTextField(name, { name = it }, label = "Название", placeholder = "Например, Хамовники Арена", maxLength = 120)
        AppTextField(address, { address = it }, label = "Адрес", placeholder = "Город, улица, дом", maxLength = 255)

        Text("Расположение на карте", style = AppType.caption, color = colors.text)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.weight(1f)) { AppTextField(latText, { latText = it }, placeholder = "Широта", keyboardType = KeyboardType.Decimal, maxLength = 12) }
            Box(Modifier.weight(1f)) { AppTextField(lonText, { lonText = it }, placeholder = "Долгота", keyboardType = KeyboardType.Decimal, maxLength = 12) }
        }
        if (mapKitReady) SecondaryButton("Выбрать точку на карте", { showPicker = true })

        Text("Тип площадки", style = AppType.caption, color = colors.text)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip("Открытая", type == "outdoor", { type = "outdoor" })
            Chip("Закрытая", type == "indoor", { type = "indoor" })
        }
        Text("Виды спорта", style = AppType.caption, color = colors.text)
        ChipFlow {
            sports.forEach { s -> Chip(s.name, s.id in chosen, { chosen = if (s.id in chosen) chosen - s.id else chosen + s.id }) }
        }
        AppTextField(hours, { hours = it }, label = "Время работы", placeholder = "08:00 - 23:00", maxLength = 100)
        AppTextField(cost, { cost = it }, label = "Стоимость", placeholder = "Бесплатно", maxLength = 100)
        AppTextField(description, { description = it }, label = "Описание", placeholder = "Покрытие, освещение, раздевалки…", singleLine = false, minLines = 3, maxLength = 2000, imeAction = ImeAction.Default)

        Text("Фотография", style = AppType.caption, color = colors.text)
        val shown: Any? = photoUri ?: container.repo.mediaUrl(venue?.photoUrl)
        if (shown != null) {
            AsyncImage(model = shown, contentDescription = "Фотография площадки", contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxWidth().height(170.dp).clip(RoundedCornerShape(12.dp)).background(colors.surface))
        }
        SecondaryButton(if (photoBusy) "Загрузка…" else if (shown != null) "Заменить фото" else "Добавить фото", { if (!photoBusy) photoLauncher.launch("image/*") })
        Text("Фото сжимается на телефоне и проверяется сервером; допустимы JPEG, PNG и WebP.", style = AppType.caption, color = colors.textSecondary)

        InlineError(error)
        PrimaryButton(
            when {
                editVenueId == null && isAdmin -> "Добавить площадку"
                editVenueId == null -> "Отправить на проверку"
                isAdmin -> "Сохранить"
                else -> "Предложить изменения"
            }, { submit(false) }, loading = busy, enabled = !photoBusy,
        )
    }

    if (showPicker) {
        PointPickerDialog(
            initial = run {
                val la = latText.replace(',', '.').toDoubleOrNull()
                val lo = lonText.replace(',', '.').toDoubleOrNull()
                if (la != null && lo != null) GeoPoint(la, lo) else null
            },
            onPick = { p -> latText = "%.6f".format(java.util.Locale.US, p.lat); lonText = "%.6f".format(java.util.Locale.US, p.lon); showPicker = false },
            onDismiss = { showPicker = false },
        )
    }

    duplicates?.let { list ->
        AppDialog({ duplicates = null }, "Похоже, такая площадка уже есть", content = {
            Text("Рядом или с таким же названием найдено:", style = AppType.small, color = colors.textSecondary)
            list.forEach { d ->
                Text("• ${d.name} — ${d.address} (${d.distanceM} м)" + if (d.kind == "submission") ", ожидает проверки" else "", style = AppType.small, color = colors.text)
            }
            Text("Если это другая площадка, отправьте всё равно.", style = AppType.small, color = colors.textSecondary)
        }) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                PrimaryButton("Это другая площадка — отправить", { duplicates = null; submit(true) })
                SecondaryButton("Вернуться к форме", { duplicates = null })
            }
        }
    }
}

private fun <T, R> ApiResult<T>.map(f: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Ok -> ApiResult.Ok(f(value))
    is ApiResult.Fail -> this
}

/** Полноэкранный выбор точки: нажмите на карту, затем «Выбрать». */
@Composable
private fun PointPickerDialog(initial: GeoPoint?, onPick: (GeoPoint) -> Unit, onDismiss: () -> Unit) {
    val container = LocalContainer.current
    var point by remember { mutableStateOf(initial) }
    val settings = container.settings.value
    val start = initial
        ?: settings?.let { s -> if (s.refLat != null && s.refLon != null) GeoPoint(s.refLat, s.refLon) else null }
        ?: GeoPoint(55.7558, 37.6173)
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(colors.background).statusBarsPadding().navigationBarsPadding()) {
            Text("Нажмите на карту, чтобы поставить точку", style = AppType.bodyBold, color = colors.text, modifier = Modifier.padding(16.dp))
            Box(Modifier.weight(1f).fillMaxWidth()) {
                YandexMap(
                    venues = emptyList(), selectedId = null, me = null, reference = point, dark = colors.dark,
                    camera = CameraRequest(1, start.lat, start.lon, if (initial != null) 16f else 12f),
                    onSelect = {}, onLongTap = { point = it }, onEmptyTap = { point = it }, modifier = Modifier.fillMaxSize(),
                )
            }
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(point?.let { "Точка: %.5f, %.5f".format(java.util.Locale.US, it.lat, it.lon) } ?: "Точка не выбрана", style = AppType.small, color = colors.textSecondary)
                PrimaryButton("Выбрать эту точку", { point?.let(onPick) }, enabled = point != null)
                SecondaryButton("Отмена", onDismiss)
            }
        }
    }
}

// ------------------------------------------------------------------ мои заявки
@Composable
fun MySubmissionsScreen() {
    val container = LocalContainer.current
    val shell = LocalShell.current
    var tab by remember { mutableStateOf(0) }
    val subs = rememberLoader { container.repo.call { it.mySubmissions() } }
    val props = rememberLoader { container.repo.call { it.myProposals() } }
    Screen("Мои заявки", onMenu = { shell.openDrawer() }) {
        Column(Modifier.fillMaxSize()) {
            TabBar(listOf("Новые площадки", "Изменения"), tab, { tab = it })
            if (tab == 0) {
                LoadView(subs, Modifier.fillMaxSize()) { resp ->
                    if (resp.items.isEmpty()) EmptyState("Заявок нет", "Здесь будут ваши предложенные площадки и решения модераторов.", action = "Предложить площадку", onAction = { shell.navigate("venue/new") })
                    else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(resp.items, key = { it.id }) { s -> SubmissionCard(s.name, s.address, s.status, s.decisionReason, s.createdAt, s.decidedAt, s.sports.joinToString { it.name }) }
                    }
                }
            } else {
                LoadView(props, Modifier.fillMaxSize()) { resp ->
                    if (resp.items.isEmpty()) EmptyState("Предложений нет", "Предложить изменения можно в карточке площадки на карте.")
                    else LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(resp.items, key = { it.id }) { p -> SubmissionCard(p.name, p.address, p.status, p.decisionReason, p.createdAt, p.decidedAt, p.sports.joinToString { it.name }) }
                    }
                }
            }
        }
    }
}

fun statusLabel(status: String) = when (status) {
    "pending" -> "На проверке"
    "approved" -> "Одобрено"
    "rejected" -> "Отклонено"
    else -> status
}

@Composable
private fun SubmissionCard(name: String, address: String, status: String, reason: String?, created: String, decided: String?, sports: String) {
    AppCard {
        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(name, style = AppType.bodyBold, color = colors.text, modifier = Modifier.weight(1f))
                Tag(statusLabel(status))
            }
            Text(address, style = AppType.small, color = colors.textSecondary)
            if (sports.isNotEmpty()) Text(sports, style = AppType.caption, color = colors.textSecondary)
            Text("Отправлено: ${formatDateTime(created)}" + if (decided != null) " · Решение: ${formatDateTime(decided)}" else "", style = AppType.caption, color = colors.textSecondary)
            if (!reason.isNullOrBlank()) Text("Причина: $reason", style = AppType.small, color = if (status == "rejected") colors.danger else colors.text)
        }
    }
}
