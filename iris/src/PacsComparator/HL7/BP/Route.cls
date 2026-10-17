Include Ensemble

/// Routes HL7 v2 from the simulated RIS into FHIR: ORM^O01 to ServiceRequest, ORU^R01 to DiagnosticReport,
/// written to Motol's FHIR endpoint by PacsComparator.BO.FhirWriter. After a ServiceRequest it calls the
/// backend hook so that the cases of the patient are checked again. Other message types are ignored
/// with a warning in the event log.
Class PacsComparator.HL7.BP.Route Extends Ens.BusinessProcess
{

Property FhirBase As %String(MAXLEN = 300) [ InitialExpression = "http://localhost:52773/fhir/r4" ];

Property Credentials As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.Iris" ];

Property HookTarget As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.HL7.BO.BackendHook" ];

Parameter SETTINGS = "FhirBase,Credentials,HookTarget";

Method OnRequest(pRequest As EnsLib.HL7.Message, Output pResponse As Ens.Response) As %Status
{
	Set type = ##class(PacsComparator.HL7.Map).MessageType(pRequest)
	If type = "ORM^O01" {
		Set json = ##class(PacsComparator.HL7.Map).ServiceRequest(pRequest, .patientId, .resourceId)
		Set resourceType = "ServiceRequest"
	} ElseIf type = "ORU^R01" {
		Set json = ##class(PacsComparator.HL7.Map).DiagnosticReport(pRequest, .patientId, .resourceId)
		Set resourceType = "DiagnosticReport"
	} Else {
		$$$LOGWARNING("HL7 message type '" _ type _ "' is not handled, ignored")
		Quit $$$OK
	}
	If json = "" Quit $$$ERROR($$$GeneralError, type _ " without patient id or order number")
	If '..PatientExists(patientId) {
		Quit $$$ERROR($$$GeneralError, type _ ": patient not found in the FHIR repository")
	}
	Set w = ##class(PacsComparator.Msg.FhirWrite).%New()
	Set w.ResourceType = resourceType, w.ResourceId = resourceId, w.Json = json
	Set sc = ..SendRequestSync("PacsComparator.BO.FhirWriter", w, .ack)
	Quit:$$$ISERR(sc) sc
	If resourceType = "ServiceRequest" {
		Set ev = ##class(PacsComparator.HL7.Msg.Written).%New()
		Set ev.PatientId = patientId, ev.ResourceType = resourceType, ev.ResourceId = resourceId
		Set sc = ..SendRequestSync(..HookTarget, ev, .hookResp)
		// the hook is best effort, a missing backend must not fail the HL7 message
		If $$$ISERR(sc) $$$LOGWARNING("backend hook: " _ $Extract($System.Status.GetErrorText(sc), 1, 200))
	}
	Quit $$$OK
}

Method PatientExists(patientId As %String) As %Boolean
{
	Set http = ##class(PacsComparator.Req.Http).New(..FhirBase, ..Credentials, .path)
	Set http.Timeout = 15
	Set sc = http.Get(path _ "/Patient/" _ $ZConvert(patientId, "O", "URL"))
	Quit $$$ISOK(sc) && (http.HttpResponse.StatusCode = 200)
}

}
