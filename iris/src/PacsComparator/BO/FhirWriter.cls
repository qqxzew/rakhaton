Include Ensemble

/// Writes FHIR resources (Task, Communication, AuditEvent) to Motol's FHIR endpoint in IRIS.
Class PacsComparator.BO.FhirWriter Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Property FhirBase As %String(MAXLEN = 300) [ InitialExpression = "http://localhost:52773/fhir/r4" ];

Property Credentials As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.Iris" ];

Parameter SETTINGS = "FhirBase,Credentials";

Method Write(pRequest As PacsComparator.Msg.FhirWrite, Output pResponse As PacsComparator.Msg.Ack) As %Status
{
	Set pResponse = ##class(PacsComparator.Msg.Ack).%New()
	Set http = ##class(PacsComparator.Req.Http).New(..FhirBase, ..Credentials, .path)
	Set http.ContentType = "application/fhir+json"
	Set http.ContentCharset = "UTF-8"
	Do http.EntityBody.Write(pRequest.Json)
	Set tSC = http.Put(path _ "/" _ pRequest.ResourceType _ "/" _ pRequest.ResourceId)
	Quit:$$$ISERR(tSC) tSC
	Set code = http.HttpResponse.StatusCode
	Set pResponse.Info = "HTTP " _ code
	If code >= 300 {
		Set pResponse.Ok = 0
		Quit $$$ERROR($$$GeneralError, "FHIR PUT " _ pRequest.ResourceType _ "/" _ pRequest.ResourceId _ " odpovědělo HTTP " _ code)
	}
	Quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="PacsComparator.Msg.FhirWrite">
    <Method>Write</Method>
  </MapItem>
</MapItems>
}

}
