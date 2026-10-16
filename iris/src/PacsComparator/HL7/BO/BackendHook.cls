Include Ensemble

/// Tells the Python backend that a ServiceRequest of a patient arrived from the RIS (POST HookUrl,
/// JSON {patient_id, resource_type, resource_id}); the backend then re-checks the cases of the patient.
Class PacsComparator.HL7.BO.BackendHook Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Property HookUrl As %String(MAXLEN = 300) [ InitialExpression = "http://host.docker.internal:8000/api/hooks/fhir-written" ];

Parameter SETTINGS = "HookUrl";

Method Notify(pRequest As PacsComparator.HL7.Msg.Written, Output pResponse As PacsComparator.Msg.Ack) As %Status
{
	Set pResponse = ##class(PacsComparator.Msg.Ack).%New()
	Set http = ##class(PacsComparator.Req.Http).New(..HookUrl, "", .path)
	Set http.Timeout = 10
	Set http.ContentType = "application/json"
	Set http.ContentCharset = "UTF-8"
	Set body = {"patient_id": (pRequest.PatientId), "resource_type": (pRequest.ResourceType), "resource_id": (pRequest.ResourceId)}
	Do http.EntityBody.Write(body.%ToJSON())
	Set tSC = http.Post(path)
	Quit:$$$ISERR(tSC) tSC
	Set code = http.HttpResponse.StatusCode
	Set pResponse.Info = "HTTP " _ code
	If code >= 300 Quit $$$ERROR($$$GeneralError, "backend hook answered HTTP " _ code)
	Quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="PacsComparator.HL7.Msg.Written">
    <Method>Notify</Method>
  </MapItem>
</MapItems>
}

}
