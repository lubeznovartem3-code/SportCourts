package ru.sportcourts.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ru.sportcourts.app.core.ApiResult
import ru.sportcourts.app.data.ReportBody
import ru.sportcourts.app.ui.LocalContainer
import ru.sportcourts.app.ui.LocalToaster

private val reasons = listOf(
    "spam" to "Спам",
    "harassment" to "Оскорбления или домогательства",
    "inappropriate" to "Неприемлемое содержимое",
    "fake_info" to "Недостоверная информация",
    "other" to "Другое",
)

/** Жалоба на пользователя, площадку или игру. Попадает к администраторам и модераторам с правом разбора жалоб. */
@Composable
fun ReportDialog(
    title: String,
    userId: Long? = null,
    venueId: Long? = null,
    gameId: Long? = null,
    onDismiss: () -> Unit,
) {
    val container = LocalContainer.current
    val toaster = LocalToaster.current
    val scope = rememberCoroutineScope()
    var reason by remember { mutableStateOf("spam") }
    var details by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    AppDialog(onDismiss, title, content = {
        ChipFlow {
            reasons.forEach { (code, label) -> Chip(label, reason == code, { reason = code }) }
        }
        AppTextField(details, { details = it }, label = "Что произошло (необязательно)", singleLine = false, minLines = 3, maxLength = 1000)
        InlineError(error)
    }) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton("Отправить жалобу", {
                busy = true
                error = null
                scope.launch {
                    val r = container.repo.call {
                        it.report(ReportBody(userId, venueId, gameId, reason, details.trim().ifEmpty { null }))
                    }
                    busy = false
                    when (r) {
                        is ApiResult.Ok -> { toaster.show("Жалоба отправлена"); onDismiss() }
                        is ApiResult.Fail -> error = r.error.message
                    }
                }
            }, loading = busy)
            SecondaryButton("Отмена", onDismiss)
        }
    }
}
