/// FHIR R4 resources that mirror a request: Task (state), Communication (messages), AuditEvent
/// (transitions, approvals, outgoing requests). Everything is tagged as simulation (hard rule 5).
Class PacsComparator.Req.Fhir Extends %RegisteredObject
{

Parameter SIMSYSTEM = "urn:pacs-comparator:simulation";

Parameter REQSYSTEM = "urn:pacs-comparator:request-id";

ClassMethod Meta() As %DynamicObject
{
	Quit {"tag": [{"system": (..#SIMSYSTEM), "code": "simulated", "display": "Simulace"}]}
}

ClassMethod TaskStatus(state As %String) As %String
{
	Quit $Case(state, "DETECTED": "draft", "DRAFTED": "draft", "APPROVED": "requested", "VERIFIED": "completed", "CLOSED": "completed", "REJECTED": "rejected", "WRONG_RECIPIENT": "rejected", "CANCELLED": "cancelled", : "in-progress")
}

ClassMethod Task(req As PacsComparator.Req.Request) As %String
{
	Set t = {"resourceType": "Task", "id": (req.RequestId)}
	Set t.meta = ..Meta()
	Set t.identifier = [{"system": (..#REQSYSTEM), "value": (req.RequestId)}]
	Set t.status = ..TaskStatus(req.State)
	Set t.businessStatus = {"text": (req.State)}
	Set t.intent = "order"
	Set t.priority = "routine"
	Set t.code = {"text": "Žádost o zaslání obrazové dokumentace"}
	Set t.description = req.Modality _ " " _ ##class(PacsComparator.Req.Templates).RegionText(req.Regions) _ " " _ req.TargetDate _ " (" _ req.ProviderName _ ", simulace)"
	Set t.focus = {"identifier": {"system": "urn:pacs-comparator:required-item", "value": (req.ItemId)}, "display": (req.Modality _ " " _ req.TargetDate)}
	If req.PatientId '= "" Set t.for = {"reference": ("Patient/" _ req.PatientId)}
	Set t.authoredOn = ##class(PacsComparator.Req.Util).Iso(req.CreatedAt)
	Set t.lastModified = ##class(PacsComparator.Req.Util).Iso(req.UpdatedAt)
	If req.ApprovedBy '= "" Set t.owner = {"display": (req.ApprovedBy)}
	If req.Deadline '= "" Set t.restriction = {"period": {"end": (req.Deadline)}}
	If req.Note '= "" Set t.note = [{"text": (req.Note)}]
	Quit t.%ToJSON()
}

ClassMethod AuditEvent(req As PacsComparator.Req.Request, actor As %String, from As %String, to As %String, note As %String, seq As %Integer) As %String
{
	Set a = {"resourceType": "AuditEvent", "id": (req.RequestId _ "-a" _ seq)}
	Set a.meta = ..Meta()
	Set a.type = {"system": "http://dicom.nema.org/resources/ontology/DCM", "code": "110100", "display": "Application Activity"}
	Set a.subtype = [{"system": "urn:pacs-comparator:request-state", "code": (to), "display": (from _ " -> " _ to)}]
	Set a.action = $Select(from = "": "C", 1: "U")
	Set a.recorded = ##class(PacsComparator.Req.Util).Iso(req.UpdatedAt)
	Set a.outcome = "0"
	Set a.agent = [{"who": {"display": ($Select(actor = "": "system", 1: actor))}, "requestor": true}]
	Set a.source = {"observer": {"display": "PacsComparator.Production"}}
	Set a.entity = [{"what": {"reference": ("Task/" _ req.RequestId)}, "description": (note)}]
	Quit a.%ToJSON()
}

/// medium: EMAILWRIT or PHONE (HL7 v3 ParticipationMode); direction out = sent, in = received.
ClassMethod Communication(req As PacsComparator.Req.Request, msgId As %String, medium As %String, direction As %String, text As %String, ts As %String) As %String
{
	Set c = {"resourceType": "Communication", "id": (req.RequestId _ "-c" _ msgId)}
	Set c.meta = ..Meta()
	Set c.status = "completed"
	Set c.basedOn = [{"reference": ("Task/" _ req.RequestId)}]
	Set c.medium = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode", "code": (medium)}]}]
	If req.PatientId '= "" Set c.subject = {"reference": ("Patient/" _ req.PatientId)}
	Set c.payload = [{"contentString": (text)}]
	If direction = "out" {
		Set c.sent = ##class(PacsComparator.Req.Util).Iso(ts)
	} Else {
		Set c.received = ##class(PacsComparator.Req.Util).Iso(ts)
	}
	Quit c.%ToJSON()
}

}
