Include Ensemble

/// State machine of a request for imaging material (CLAUDE.md 10.2). One Event message per call:
/// DRAFT, APPROVE, TICK (timers), REPLY, CALL_OUTCOME, DELIVERY, CANCEL, CLOSE.
/// The business process owns every transition: it persists Req.Request / Req.Event, sends email,
/// voice and hospital FHIR messages through the business operations and mirrors the state into the
/// FHIR Task (plus AuditEvent and Communication). Nothing is sent before an approval is recorded.
Class PacsComparator.BP.RequestLifecycle Extends Ens.BusinessProcess
{

Parameter SETTINGS = "TimerProfile,ReminderAfterSeconds,VoiceAfterSeconds,HumanAfterSeconds,DemoSeconds,LlmBaseUrl,LlmModel,LlmCredentials";

/// normal: the *AfterSeconds settings; demo: every timer is DemoSeconds
Property TimerProfile As %String(VALUELIST = ",normal,demo") [ InitialExpression = "normal" ];

/// Reminder this long after SENT
Property ReminderAfterSeconds As %Integer [ InitialExpression = 86400 ];

/// Voice escalation this long after the reminder
Property VoiceAfterSeconds As %Integer [ InitialExpression = 86400 ];

/// Hand over to a human this long after the voice call without an outcome
Property HumanAfterSeconds As %Integer [ InitialExpression = 86400 ];

Property DemoSeconds As %Integer [ InitialExpression = 20 ];

Property LlmBaseUrl As %String(MAXLEN = 300) [ InitialExpression = "https://apim-rakathon-q7146n.azure-api.net/openai/v1/" ];

Property LlmModel As %String(MAXLEN = 100) [ InitialExpression = "gpt-6-luna-dz-eu" ];

Property LlmCredentials As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.Llm" ];

Method OnRequest(pRequest As PacsComparator.Msg.Event, Output pResponse As PacsComparator.Msg.Result) As %Status
{
	Set pResponse = ##class(PacsComparator.Msg.Result).%New()
	Set pResponse.RequestId = pRequest.RequestId
	Set tKey = $Select(pRequest.RequestId = "": "new", 1: pRequest.RequestId)
	Lock +^PacsComparator.Lock(tKey):15
	If '$Test Quit $$$ERROR($$$GeneralError, "Žádost je právě zpracovávána, zkuste to znovu")
	Try {
		Set tSC = ..Dispatch(pRequest, pResponse)
	} Catch ex {
		Set tSC = ex.AsStatus()
	}
	Lock -^PacsComparator.Lock(tKey)
	Quit tSC
}

Method Dispatch(pReq As PacsComparator.Msg.Event, pResp As PacsComparator.Msg.Result) As %Status
{
	Set action = pReq.Action
	If action = "DRAFT" Quit ..DoDraft(pReq, pResp)
	Set req = ##class(PacsComparator.Req.Request).RequestIdIdxOpen(pReq.RequestId)
	If '$IsObject(req) Quit $$$ERROR($$$GeneralError, "Neznámá žádost " _ pReq.RequestId)
	If action = "APPROVE" Quit ..DoApprove(req, pReq, pResp)
	If action = "TICK" Quit ..DoTick(req, pResp)
	If action = "REPLY" Quit ..DoReply(req, pReq, pResp)
	If action = "CALL_OUTCOME" Quit ..DoCallOutcome(req, pReq, pResp)
	If action = "DELIVERY" Quit ..DoDelivery(req, pReq, pResp)
	If action = "CANCEL" Quit ..DoSimpleMove(req, "CANCELLED", pReq.Actor, "Žádost zrušena (položka odpuštěna)", pResp)
	If action = "CLOSE" Quit ..DoSimpleMove(req, "CLOSED", pReq.Actor, "Žádost uzavřena", pResp)
	Quit $$$ERROR($$$GeneralError, "Neznámá akce " _ action)
}

// ---- actions ----

Method DoDraft(pReq As PacsComparator.Msg.Event, pResp As PacsComparator.Msg.Result) As %Status
{
	Set p = ##class(%DynamicAbstractObject).%FromJSON(pReq.Payload)
	Set existing = ..ActiveForItem(p.%Get("itemId"))
	If existing '= "" {
		Set req = ##class(PacsComparator.Req.Request).RequestIdIdxOpen(existing)
		Do ..Fill(req, pResp, "Pro tuto položku už žádost existuje")
		Quit $$$OK
	}
	Set now = ##class(PacsComparator.Req.Util).Now()
	Set req = ##class(PacsComparator.Req.Request).%New()
	Set seq = $Increment(^PacsComparator.Req("seq"))
	Set req.RequestId = "PACS-REQ-" _ $Translate($Justify(seq + 99, 6), " ", "0")
	Set req.FhirTaskId = req.RequestId
	Set req.ItemId = p.%Get("itemId"), req.CaseId = p.%Get("caseId"), req.PatientId = p.%Get("patientId")
	Set req.ProviderId = p.%Get("providerId"), req.ProviderName = p.%Get("providerName")
	Set req.ProviderEmail = p.%Get("providerEmail"), req.ProviderPhone = p.%Get("providerPhone")
	Set req.ProviderRoute = p.%Get("providerRoute"), req.StudyRef = p.%Get("studyRef")
	Set req.Modality = p.%Get("modality"), req.Regions = p.%Get("regions"), req.TargetDate = p.%Get("targetDate")
	Set req.AccessionRef = p.%Get("accessionRef"), req.Deadline = p.%Get("deadline")
	Set req.State = "DETECTED", req.CreatedAt = now
	Do ..Touch(req)
	Set tSC = req.%Save()
	Quit:$$$ISERR(tSC) tSC
	Do ..Record(req.RequestId, "system", "", "DETECTED", "Chybějící studie zjištěna")
	Do ..Mirror(req, "system", "", "DETECTED", "Chybějící studie zjištěna")
	Set tSC = ..Move(req, "DRAFTED", "system", "Koncept žádosti připraven, čeká na schválení")
	Quit:$$$ISERR(tSC) tSC
	Do ..Fill(req, pResp, "")
	Quit $$$OK
}

Method DoApprove(req As PacsComparator.Req.Request, pReq As PacsComparator.Msg.Event, pResp As PacsComparator.Msg.Result) As %Status
{
	If req.State '= "DRAFTED" Quit $$$ERROR($$$GeneralError, "Schválit lze jen koncept (stav je " _ req.State _ ")")
	If pReq.Actor = "" Quit $$$ERROR($$$GeneralError, "Schválení vyžaduje jméno koordinátora")
	Set now = ##class(PacsComparator.Req.Util).Now()
	Set req.ApprovedBy = pReq.Actor, req.ApprovedAt = now, req.NextActionAt = now
	Set tSC = ..Move(req, "APPROVED", pReq.Actor, "Schváleno koordinátorem " _ pReq.Actor)
	Quit:$$$ISERR(tSC) tSC
	Quit ..DoSend(req, pResp)
}

/// APPROVED -> SENT. Never sends without a recorded approval.
Method DoSend(req As PacsComparator.Req.Request, pResp As PacsComparator.Msg.Result) As %Status
{
	If (req.ApprovedBy = "") || (req.ApprovedAt = "") Quit $$$ERROR($$$GeneralError, "Odeslání bez schválení koordinátorem není povoleno")
	Set now = ##class(PacsComparator.Req.Util).Now()
	Set tSC = ..SendMail(req, 0)
	If $$$ISERR(tSC) {
		Set req.Note = "Odeslání selhalo, zkusíme znovu: " _ $Extract($System.Status.GetErrorText(tSC), 1, 300)
		Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, 60)
		Do ..Touch(req)
		Do req.%Save()
		$$$LOGWARNING(req.Note)
		Do ..Fill(req, pResp, req.Note)
		Quit $$$OK
	}
	Set req.Attempts = req.Attempts + 1, req.SentAt = now
	Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, ..Delay("reminder"))
	Set tSC = ..Move(req, "SENT", "system", "E-mail odeslán: " _ req.ProviderName)
	Quit:$$$ISERR(tSC) tSC
	Do ..Fill(req, pResp, "")
	Quit $$$OK
}

Method DoTick(req As PacsComparator.Req.Request, pResp As PacsComparator.Msg.Result) As %Status
{
	Set now = ##class(PacsComparator.Req.Util).Now()
	If (req.NextActionAt = "") || (req.NextActionAt ] now) {
		Do ..Fill(req, pResp, "Nic není splatné")
		Quit $$$OK
	}
	Set state = req.State
	If state = "APPROVED" Quit ..DoSend(req, pResp)
	If state = "SENT" {
		Set tSC = ..SendMail(req, 1)
		If $$$ISERR(tSC) {
			Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, 60)
			Set req.Note = "Odeslání připomínky selhalo: " _ $Extract($System.Status.GetErrorText(tSC), 1, 300)
			Do ..Touch(req)
			Do req.%Save()
			Quit $$$OK
		}
		Set req.Attempts = req.Attempts + 1
		Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, ..Delay("voice"))
		Set tSC = ..Move(req, "REMINDER_SENT", "system", "Bez odpovědi, odeslána připomínka")
	} ElseIf state = "REMINDER_SENT" {
		Set v = ##class(PacsComparator.Msg.Voice).%New()
		Set v.RequestId = req.RequestId, v.Phone = req.ProviderPhone
		Set v.Script = ##class(PacsComparator.Req.Templates).VoiceScript(req)
		Set tSC = ..SendRequestSync("PacsComparator.BO.Voice", v, .ack)
		If $$$ISERR(tSC) {
			Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, 60)
			Set req.Note = "Hlasová eskalace selhala: " _ $Extract($System.Status.GetErrorText(tSC), 1, 300)
			Do ..Touch(req)
			Do req.%Save()
			Quit $$$OK
		}
		Do ..Comm(req, ack.MessageId, "PHONE", "out", v.Script)
		Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, ..Delay("human"))
		Set tSC = ..Move(req, "VOICE_ESCALATED", "system", "Stále bez odpovědi, hlasová eskalace (simulace)")
	} ElseIf state = "VOICE_ESCALATED" {
		Set req.NextActionAt = ""
		Set tSC = ..Move(req, "HUMAN_ESCALATED", "system", "Hovor bez výsledku, předáno koordinátorovi")
	} Else {
		Set tSC = $$$OK
	}
	Quit:$$$ISERR(tSC) tSC
	Do ..Fill(req, pResp, "")
	Quit $$$OK
}

Method DoReply(req As PacsComparator.Req.Request, pReq As PacsComparator.Msg.Event, pResp As PacsComparator.Msg.Result) As %Status
{
	Set text = ##class(%DynamicAbstractObject).%FromJSON(pReq.Payload).%Get("text")
	If text = "" Quit $$$ERROR($$$GeneralError, "Prázdná odpověď")
	If '..CanReceive(req.State) Quit $$$ERROR($$$GeneralError, "Odpověď nelze zpracovat ve stavu " _ req.State)
	Set key = ""
	Set sc = ##class(Ens.Config.Credentials).GetCredentialsObj(.cred, ..%ClassName(1), "Ens.Config.Credentials", ..LlmCredentials)
	If $$$ISOK(sc) Set key = cred.Password
	Set rc = ##class(%DynamicAbstractObject).%FromJSON(##class(PacsComparator.Req.Logic).Classify(text, ..LlmBaseUrl, key, ..LlmModel))
	Set class = rc.%Get("class"), quote = rc.%Get("quote")
	Set msgId = ..AddMessage(req.RequestId, "reply", "in", "email", "Odpověď poskytovatele (simulace)", text, class, quote, rc.%Get("method"))
	Do ..Comm(req, msgId, "EMAILWRIT", "in", text)
	Set target = $Case(class, "sent": "ACKNOWLEDGED", "will_send_later": "ACKNOWLEDGED", "not_here": "REJECTED", "need_more_info": "NEEDS_INFO", "wrong_recipient": "WRONG_RECIPIENT", : "")
	Set req.ReplyClass = class
	Set note = "Odpověď zařazena jako " _ class _ $Select(quote '= "": " (citace: " _ quote _ ")", 1: "")
	If (target = "") || (target = req.State) {
		Set req.Note = note
		Do ..Touch(req)
		Do req.%Save()
		Do ..Record(req.RequestId, "provider-sim", req.State, req.State, note)
		Do ..Mirror(req, "provider-sim", req.State, req.State, note)
		Do ..Fill(req, pResp, note)
		Quit $$$OK
	}
	Set req.NextActionAt = ""
	Set tSC = ..Move(req, target, "provider-sim", note)
	Quit:$$$ISERR(tSC) tSC
	Do ..Fill(req, pResp, note)
	Quit $$$OK
}

Method DoCallOutcome(req As PacsComparator.Req.Request, pReq As PacsComparator.Msg.Event, pResp As PacsComparator.Msg.Result) As %Status
{
	If req.State '= "VOICE_ESCALATED" Quit $$$ERROR($$$GeneralError, "Výsledek hovoru lze zadat jen po hlasové eskalaci (stav je " _ req.State _ ")")
	Set outcome = ##class(%DynamicAbstractObject).%FromJSON(pReq.Payload).%Get("outcome")
	If '$ListFind($ListBuild("accepted", "call_back", "refused", "no_answer"), outcome) Quit $$$ERROR($$$GeneralError, "Neznámý výsledek hovoru " _ outcome)
	Set now = ##class(PacsComparator.Req.Util).Now()
	Set msgId = ..AddMessage(req.RequestId, "call_outcome", "in", "phone", "Výsledek hovoru (simulace)", outcome, outcome, "", "")
	Do ..Comm(req, msgId, "PHONE", "in", "Výsledek hovoru: " _ outcome)
	If outcome = "accepted" {
		Set req.NextActionAt = ""
		Set tSC = ..Move(req, "ACKNOWLEDGED", "provider-sim", "Hovor: pracoviště žádost přijalo")
	} ElseIf outcome = "call_back" {
		Set req.NextActionAt = ##class(PacsComparator.Req.Util).AddSeconds(now, ..Delay("human"))
		Set req.Note = "Hovor: pracoviště zavolá zpět"
		Do ..Touch(req)
		Do req.%Save()
		Do ..Record(req.RequestId, "provider-sim", req.State, req.State, req.Note)
		Do ..Mirror(req, "provider-sim", req.State, req.State, req.Note)
		Set tSC = $$$OK
	} Else {
		Set req.NextActionAt = ""
		Set tSC = ..Move(req, "HUMAN_ESCALATED", "provider-sim", "Hovor neúspěšný (" _ outcome _ "), předáno koordinátorovi")
	}
	Quit:$$$ISERR(tSC) tSC
	Do ..Fill(req, pResp, "")
	Quit $$$OK
}

Method DoDelivery(req As PacsComparator.Req.Request, pReq As PacsComparator.Msg.Event, pResp As PacsComparator.Msg.Result) As %Status
{
	If '..CanReceive(req.State) && (req.State '= "RECEIVED") Quit $$$ERROR($$$GeneralError, "Doručení nelze zpracovat ve stavu " _ req.State)
	Set p = ##class(%DynamicAbstractObject).%FromJSON($Select(pReq.Payload = "": "{}", 1: pReq.Payload))
	Set dm = p.%Get("modality"), dd = p.%Get("date"), dr = p.%Get("region"), source = "zadáno ručně (simulace)"
	If (dm = "") || (dd = "") {
		Set q = ##class(PacsComparator.Msg.HospitalQuery).%New()
		Set q.RequestId = req.RequestId
		Set tSC = ..SendRequestSync("PacsComparator.BO.HospitalFhir", q, .hr)
		Quit:$$$ISERR(tSC) tSC
		If 'hr.Found Quit $$$ERROR($$$GeneralError, "Dodávka (MHD DocumentReference) pro " _ req.RequestId _ " nebyla nalezena")
		Set dm = hr.Modality, dd = hr.StudyDate, source = "IHE MHD DocumentReference/" _ hr.DocumentId
	}
	Set msgId = ..AddMessage(req.RequestId, "delivery", "in", "fhir", "Doručení studie (simulace)", dm _ " " _ dd _ " " _ dr _ " [" _ source _ "]", "", "", "")
	Set req.NextActionAt = ""
	If req.State '= "RECEIVED" {
		Set tSC = ..Move(req, "RECEIVED", "provider-sim", "Doručena studie " _ dm _ " " _ dd _ " (" _ source _ ")")
		Quit:$$$ISERR(tSC) tSC
	}
	Set v = ##class(%DynamicAbstractObject).%FromJSON(##class(PacsComparator.Req.Logic).Verify(req.Modality, req.TargetDate, req.Regions, dm, dd, dr))
	If v.%Get("ok") {
		Set req.VerifyReason = ""
		Set tSC = ..Move(req, "VERIFIED", "system", "Ověřeno: doručená studie odpovídá žádosti")
		Quit:$$$ISERR(tSC) tSC
		Do ..Fill(req, pResp, "")
		Quit $$$OK
	}
	Set why = ""
	Set it = v.reasons.%GetIterator()
	While it.%GetNext(.k, .reason) {
		Set why = why _ $Select(why = "": "", 1: "; ") _ reason
	}
	Set req.VerifyReason = "Doručená studie neodpovídá žádosti (" _ why _ ")"
	Set req.Note = req.VerifyReason
	Do ..Touch(req)
	Do req.%Save()
	Do ..Record(req.RequestId, "system", req.State, req.State, req.VerifyReason)
	Do ..Mirror(req, "system", req.State, req.State, req.VerifyReason)
	Do ..Fill(req, pResp, req.VerifyReason)
	Quit $$$OK
}

Method DoSimpleMove(req As PacsComparator.Req.Request, to As %String, actor As %String, note As %String, pResp As PacsComparator.Msg.Result) As %Status
{
	Set req.NextActionAt = ""
	Set tSC = ..Move(req, to, $Select(actor = "": "system", 1: actor), note)
	Quit:$$$ISERR(tSC) tSC
	Do ..Fill(req, pResp, "")
	Quit $$$OK
}

// ---- helpers ----

ClassMethod Allowed(from As %String, to As %String) As %Boolean
{
	Set active = "ACKNOWLEDGED,RECEIVED,REJECTED,NEEDS_INFO,WRONG_RECIPIENT,CANCELLED"
	Set t = $Case(from, "": "DETECTED", "DETECTED": "DRAFTED,CANCELLED", "DRAFTED": "APPROVED,CANCELLED", "APPROVED": "SENT,CANCELLED", "SENT": "REMINDER_SENT," _ active, "REMINDER_SENT": "VOICE_ESCALATED," _ active, "VOICE_ESCALATED": "HUMAN_ESCALATED," _ active, "HUMAN_ESCALATED": active, "ACKNOWLEDGED": "RECEIVED,NEEDS_INFO,CANCELLED", "RECEIVED": "VERIFIED,CANCELLED", "VERIFIED": "CLOSED", "NEEDS_INFO": "ACKNOWLEDGED,RECEIVED,CANCELLED", : "")
	Quit ("," _ t _ ",") [ ("," _ to _ ",")
}

/// States in which a provider reply or delivery makes sense (the request has been sent).
ClassMethod CanReceive(state As %String) As %Boolean
{
	Quit ",SENT,REMINDER_SENT,VOICE_ESCALATED,HUMAN_ESCALATED,ACKNOWLEDGED,NEEDS_INFO," [ ("," _ state _ ",")
}

Method Delay(kind As %String) As %Integer
{
	If ..TimerProfile = "demo" Quit ..DemoSeconds
	Quit $Case(kind, "reminder": ..ReminderAfterSeconds, "voice": ..VoiceAfterSeconds, : ..HumanAfterSeconds)
}

ClassMethod ActiveForItem(itemId As %String) As %String
{
	If itemId = "" Quit ""
	Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT RequestId FROM PacsComparator_Req.Request WHERE ItemId = ? AND State NOT IN ('REJECTED','CLOSED','CANCELLED','WRONG_RECIPIENT')", itemId)
	If rs.%Next() Quit rs.%Get("RequestId")
	Quit ""
}

Method Touch(req As PacsComparator.Req.Request)
{
	Set req.UpdatedAt = ##class(PacsComparator.Req.Util).Now()
	Set sid = ..%SessionId
	If (sid '= "") && ('$ListFind($ListFromString(req.SessionIds, ","), sid)) {
		Set req.SessionIds = req.SessionIds _ $Select(req.SessionIds = "": "", 1: ",") _ sid
	}
}

Method Move(req As PacsComparator.Req.Request, to As %String, actor As %String, note As %String) As %Status
{
	Set from = req.State
	If '..Allowed(from, to) Quit $$$ERROR($$$GeneralError, "Neplatný přechod " _ from _ " -> " _ to)
	Set req.State = to, req.Note = note
	Do ..Touch(req)
	Set tSC = req.%Save()
	Quit:$$$ISERR(tSC) tSC
	Do ..Record(req.RequestId, actor, from, to, note)
	Do ..Mirror(req, actor, from, to, note)
	Quit $$$OK
}

Method Record(requestId As %String, actor As %String, from As %String, to As %String, note As %String)
{
	Set e = ##class(PacsComparator.Req.Event).%New()
	Set e.RequestId = requestId, e.Ts = ##class(PacsComparator.Req.Util).Now(), e.Actor = actor
	Set e.FromState = from, e.ToState = to, e.Note = note, e.SessionId = ..%SessionId
	Do e.%Save()
}

/// Task (status + businessStatus) and AuditEvent in FHIR. A failing mirror is logged, it does not undo the state.
Method Mirror(req As PacsComparator.Req.Request, actor As %String, from As %String, to As %String, note As %String)
{
	Set seq = $Increment(^PacsComparator.Req("aud", req.RequestId))
	Do ..Put("Task", req.RequestId, ##class(PacsComparator.Req.Fhir).Task(req))
	Do ..Put("AuditEvent", req.RequestId _ "-a" _ seq, ##class(PacsComparator.Req.Fhir).AuditEvent(req, actor, from, to, note, seq))
}

Method Comm(req As PacsComparator.Req.Request, msgId As %String, medium As %String, direction As %String, text As %String)
{
	Set ts = ##class(PacsComparator.Req.Util).Now()
	Do ..Put("Communication", req.RequestId _ "-c" _ msgId, ##class(PacsComparator.Req.Fhir).Communication(req, msgId, medium, direction, text, ts))
}

Method Put(type As %String, id As %String, json As %String)
{
	Set m = ##class(PacsComparator.Msg.FhirWrite).%New()
	Set m.ResourceType = type, m.ResourceId = id, m.Json = json
	Set sc = ..SendRequestSync("PacsComparator.BO.FhirWriter", m, .ack)
	If $$$ISERR(sc) {
		$$$LOGWARNING("FHIR " _ type _ "/" _ id _ " nebylo zapsáno: " _ $Extract($System.Status.GetErrorText(sc), 1, 300))
	}
}

Method SendMail(req As PacsComparator.Req.Request, reminder As %Boolean) As %Status
{
	If req.ProviderEmail = "" Quit $$$ERROR($$$GeneralError, "Pracoviště nemá e-mail, koordinátor musí vybrat pracoviště")
	Set m = ##class(PacsComparator.Msg.Email).%New()
	Set m.RequestId = req.RequestId, m.To = req.ProviderEmail
	Set m.Subject = ##class(PacsComparator.Req.Templates).Subject(req, reminder)
	Set m.Body = ##class(PacsComparator.Req.Templates).Body(req, reminder)
	Set sc = ..SendRequestSync("PacsComparator.BO.Email", m, .ack)
	Quit:$$$ISERR(sc) sc
	Set msgId = ..AddMessage(req.RequestId, $Select(reminder: "reminder", 1: "email"), "out", "email", m.Subject, m.Body, "", "", "")
	Do ..Comm(req, msgId, "EMAILWRIT", "out", m.Subject _ $Char(10) _ m.Body)
	Quit $$$OK
}

ClassMethod AddMessage(requestId As %String, kind As %String, direction As %String, channel As %String, subject As %String, body As %String, class As %String, quote As %String, method As %String) As %String
{
	Set m = ##class(PacsComparator.Req.Message).%New()
	Set m.RequestId = requestId, m.Ts = ##class(PacsComparator.Req.Util).Now(), m.Kind = kind
	Set m.Direction = direction, m.Channel = channel, m.Subject = subject, m.Body = body
	Set m.ReplyClass = class, m.Quote = quote, m.ParseMethod = method
	Do m.%Save()
	Quit m.%Id()
}

ClassMethod Fill(req As PacsComparator.Req.Request, pResp As PacsComparator.Msg.Result, note As %String)
{
	Set pResp.RequestId = req.RequestId, pResp.State = req.State
	Set pResp.Note = $Select(note '= "": note, 1: req.Note)
}

}
