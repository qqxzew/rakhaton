/// Read side and demo controls of the request loop for the Python backend (native API).
/// All methods return JSON strings.
Class PacsComparator.Req.Api Extends %RegisteredObject
{

/// Comma separated ids of requests whose next action is due (in the demo clock).
ClassMethod DueIds() As %String
{
	Set now = ##class(PacsComparator.Req.Util).Now(), out = ""
	Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT RequestId FROM PacsComparator_Req.Request WHERE State IN ('APPROVED','SENT','REMINDER_SENT','VOICE_ESCALATED') AND NextActionAt IS NOT NULL AND NextActionAt <> '' AND NextActionAt <= ? ORDER BY NextActionAt", now)
	While rs.%Next() {
		Set out = out _ $Select(out = "": "", 1: ",") _ rs.%Get("RequestId")
	}
	Quit out
}

/// Runs the timers once for everything that is due; returns the results of the lifecycle calls.
ClassMethod TickDue() As %String
{
	Set arr = []
	Set ids = ..DueIds()
	For i = 1:1:$Length(ids, ",") {
		Set id = $Piece(ids, ",", i)
		If id = "" Continue
		Do arr.%Push({}.%FromJSON(##class(PacsComparator.BS.RequestIntake).Submit("TICK", id, "", "system")))
	}
	Quit arr.%ToJSON()
}

/// Moves the demo clock forward by `hours`, then runs the timers once.
ClassMethod AdvanceTime(hours As %Numeric) As %String
{
	Set ^PacsComparator.Clock("offset") = ##class(PacsComparator.Req.Util).OffsetSeconds() + (hours * 3600)
	Set out = {"offsetSeconds": (##class(PacsComparator.Req.Util).OffsetSeconds()), "now": (##class(PacsComparator.Req.Util).Now())}
	Set out.ticked = [].%FromJSON(..TickDue())
	Quit out.%ToJSON()
}

ClassMethod ResetClock() As %String
{
	Kill ^PacsComparator.Clock
	Quit {"offsetSeconds": 0}.%ToJSON()
}

ClassMethod Summary(req As PacsComparator.Req.Request) As %DynamicObject
{
	Set o = {"requestId": (req.RequestId), "itemId": (req.ItemId), "caseId": (req.CaseId)}
	Set o.state = req.State, o.modality = req.Modality, o.targetDate = req.TargetDate
	Set o.regions = $ListToString($ListFromString(req.Regions, ","), ",")
	Set o.provider = {"id": (req.ProviderId), "name": (req.ProviderName), "email": (req.ProviderEmail), "route": (req.ProviderRoute)}
	Set o.deadline = req.Deadline, o.approvedBy = req.ApprovedBy, o.approvedAt = req.ApprovedAt
	Set o.attempts = req.Attempts, o.nextActionAt = req.NextActionAt, o.updatedAt = req.UpdatedAt
	Set o.fhirTaskId = req.FhirTaskId, o.note = req.Note, o.replyClass = req.ReplyClass, o.verifyReason = req.VerifyReason
	Set o.sessionIds = $ListToString($ListFromString(req.SessionIds, ","), ",")
	Set o.simulated = 1
	Quit o
}

ClassMethod Get(requestId As %String) As %String
{
	Set req = ##class(PacsComparator.Req.Request).RequestIdIdxOpen(requestId)
	If '$IsObject(req) Quit {"found": false}.%ToJSON()
	Set o = ..Summary(req)
	Set o.found = 1
	Set o.history = []
	Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT Ts, Actor, FromState, ToState, Note, SessionId FROM PacsComparator_Req.Event WHERE RequestId = ? ORDER BY ID", requestId)
	While rs.%Next() {
		Do o.history.%Push({"ts": (rs.%Get("Ts")), "actor": (rs.%Get("Actor")), "from": (rs.%Get("FromState")), "to": (rs.%Get("ToState")), "note": (rs.%Get("Note")), "sessionId": (rs.%Get("SessionId"))})
	}
	Set o.messages = []
	Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT ID FROM PacsComparator_Req.Message WHERE RequestId = ? ORDER BY ID", requestId)
	While rs.%Next() {
		Set m = ##class(PacsComparator.Req.Message).%OpenId(rs.%Get("ID"))
		Do o.messages.%Push({"id": (m.%Id()), "ts": (m.Ts), "kind": (m.Kind), "direction": (m.Direction), "channel": (m.Channel), "subject": (m.Subject), "body": (m.Body), "class": (m.ReplyClass), "quote": (m.Quote), "method": (m.ParseMethod), "hasAudio": (m.Audio.Size > 0)})
	}
	Quit o.%ToJSON()
}

/// Summaries of the requests of one case (or all requests when caseId is empty).
ClassMethod List(caseId As %String = "") As %String
{
	Set arr = []
	If caseId = "" {
		Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT RequestId FROM PacsComparator_Req.Request ORDER BY ID")
	} Else {
		Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT RequestId FROM PacsComparator_Req.Request WHERE CaseId = ? ORDER BY ID", caseId)
	}
	While rs.%Next() {
		Do arr.%Push(..Summary(##class(PacsComparator.Req.Request).RequestIdIdxOpen(rs.%Get("RequestId"))))
	}
	Quit arr.%ToJSON()
}

/// Request ids in a draft state, optionally of one case: used by "approve all".
ClassMethod DraftIds(caseIds As %String = "") As %String
{
	Set out = ""
	Set rs = ##class(%SQL.Statement).%ExecDirect(, "SELECT RequestId, CaseId FROM PacsComparator_Req.Request WHERE State = 'DRAFTED' ORDER BY ID")
	While rs.%Next() {
		If (caseIds '= "") && (("," _ caseIds _ ",") '[ ("," _ rs.%Get("CaseId") _ ",")) Continue
		Set out = out _ $Select(out = "": "", 1: ",") _ rs.%Get("RequestId")
	}
	Quit out
}

/// Base64 of the mp3 of a stored voice message.
ClassMethod Audio(messageId As %String) As %String
{
	Set m = ##class(PacsComparator.Req.Message).%OpenId(messageId)
	If '$IsObject(m) || (m.Audio.Size = 0) Quit ""
	Set out = "", s = m.Audio
	Do s.Rewind()
	While 's.AtEnd {
		Set out = out _ $System.Encryption.Base64Encode(s.Read(30000), 1)
	}
	Quit out
}

}
