Include Ensemble

/// Receiving side of the IHE MHD delivery: searches Motol's FHIR endpoint for the DocumentReference
/// (ITI-65 Provide Document Bundle) that carries the request id and resolves the provider's
/// ImagingStudy it points to. Only references into the same FHIR server are dereferenced.
Class PacsComparator.BO.HospitalFhir Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Property MotolBase As %String(MAXLEN = 300) [ InitialExpression = "http://localhost:52773/fhir/r4" ];

Property Credentials As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.Iris" ];

Parameter SETTINGS = "MotolBase,Credentials";

Method FindDelivery(pRequest As PacsComparator.Msg.HospitalQuery, Output pResponse As PacsComparator.Msg.HospitalResult) As %Status
{
	Set pResponse = ##class(PacsComparator.Msg.HospitalResult).%New()
	Set http = ##class(PacsComparator.Req.Http).New(..MotolBase, ..Credentials, .path)
	Do http.SetParam("identifier", "urn:pacs-comparator:request-id|" _ pRequest.RequestId)
	Set tSC = http.Get(path _ "/DocumentReference")
	Quit:$$$ISERR(tSC) tSC
	If http.HttpResponse.StatusCode >= 300 Quit $$$ERROR($$$GeneralError, "Hledání DocumentReference: HTTP " _ http.HttpResponse.StatusCode)
	Set bundle = ##class(PacsComparator.Req.Http).Body(http)
	If '$IsObject(bundle) || (bundle.%Get("total") = 0) || ('$IsObject(bundle.%Get("entry"))) {
		Set pResponse.Note = "Žádná dodávka s tímto číslem žádosti"
		Quit $$$OK
	}
	Set doc = bundle.entry.%Get(0).resource
	Set pResponse.DocumentId = doc.id
	Set related = ""
	If $IsObject(doc.context) && $IsObject(doc.context.related) {
		Set it = doc.context.related.%GetIterator()
		While it.%GetNext(.k, .r) {
			If r.reference [ "ImagingStudy/" Set related = r.reference Quit
		}
	}
	If related = "" Quit $$$OK
	Set pResponse.StudyRef = related
	Set origin = ##class(PacsComparator.Req.Http).Origin(..MotolBase)
	If $Extract(related, 1, $Length(origin) + 1) '= (origin _ "/") {
		Set pResponse.Note = "Reference mimo FHIR server se nevyhodnocuje"
		Quit $$$OK
	}
	Set sh = ##class(PacsComparator.Req.Http).New(related, ..Credentials, .spath)
	Set tSC = sh.Get(spath)
	Quit:$$$ISERR(tSC) tSC
	If sh.HttpResponse.StatusCode >= 300 {
		Set pResponse.Note = "ImagingStudy poskytovatele nelze načíst (HTTP " _ sh.HttpResponse.StatusCode _ ")"
		Quit $$$OK
	}
	Set study = ##class(PacsComparator.Req.Http).Body(sh)
	If '$IsObject(study) Quit $$$OK
	If $IsObject(study.modality) {
		Set it = study.modality.%GetIterator()
		While it.%GetNext(.k, .c) {
			Set pResponse.Modality = $Case($ZConvert(c.code, "U"), "CR": "RTG", "DX": "RTG", "PT": "PET", "PET": "PET", "NM": "SCINT", "MG": "MAMO", "US": "SONO", "CT": "CT", "MR": "MR", : "")
			If pResponse.Modality '= "" Quit
		}
	}
	Set pResponse.StudyDate = $Extract(study.started, 1, 10)
	Set pResponse.Found = 1
	Quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="PacsComparator.Msg.HospitalQuery">
    <Method>FindDelivery</Method>
  </MapItem>
</MapItems>
}

}
