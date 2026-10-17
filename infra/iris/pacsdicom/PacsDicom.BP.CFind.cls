Include EnsDICOM

/// Business process: runs one study level C-FIND against the PACS named in the request (T087).
/// Flow: private session with the operation "CFind.<Target>" -> association -> C-FIND-RQ -> collect the
/// pending C-FIND-RSP identifiers -> release -> reply with PacsDicom.Msg.CFindResponse.
Class PacsDicom.BP.CFind Extends EnsLib.DICOM.Process
{

Property Duplex As %String;

Property QueryTarget As %String;

Property QueryPatientID As %String(MAXLEN = 64);

Property QueryStudyDate As %String;

Property QueryModality As %String;

Property Collected As %String(MAXLEN = "");

Property Replied As %Boolean [ InitialExpression = 0 ];

Method OnMessage(pSourceConfigName As %String, pInput As %Library.Persistent) As %Status
{
	If pInput.%IsA("PacsDicom.Msg.CFindRequest") {
		Set ..QueryTarget = pInput.Target, ..QueryPatientID = pInput.PatientID
		Set ..QueryStudyDate = pInput.StudyDate, ..QueryModality = pInput.Modality
		Set ..Duplex = "CFind." _ pInput.Target, ..Collected = "[]"
		Quit ..EstablishAssociation(..Duplex)
	}
	If pInput.%IsA("EnsLib.DICOM.Document") Quit ..HandleDocument(pInput)
	Quit $$$OK
}

Method OnAssociationEstablished(pSourceConfigName As %String, pInput As EnsLib.DICOM.Notify.Established) As %Status
{
	Set tReq = ##class(PacsDicom.Msg.CFindRequest).%New()
	Set tReq.PatientID = ..QueryPatientID, tReq.StudyDate = ..QueryStudyDate, tReq.Modality = ..QueryModality
	Set tSC = ##class(PacsDicom.BO.CFind).BuildQuery(tReq, "", .tDoc)
	If $$$ISOK(tSC) Set tSC = ..SendRequestAsync(..Duplex, tDoc, 0)
	If $$$ISERR(tSC) Quit ..Finish("ERROR", $System.Status.GetErrorText(tSC))
	Quit $$$OK
}

Method HandleDocument(pDoc As EnsLib.DICOM.Document) As %Status
{
	Set tType = $$$MsgTyp2Str(pDoc.GetValueAt("CommandSet.CommandField"))
	If tType '= "C-FIND-RSP" Quit $$$OK
	Set tStatus = +pDoc.GetValueAt("CommandSet.Status")
	#; 0xFF00 / 0xFF01 = pending with a matching identifier; 0 = success, query complete
	If (tStatus = 65280) || (tStatus = 65281) {
		Set tArr = ##class(%DynamicArray).%FromJSON(..Collected)
		Do tArr.%Push(##class(PacsDicom.BO.CFind).ReadMatch(pDoc))
		Set ..Collected = tArr.%ToJSON()
		Quit $$$OK
	}
	If tStatus = 0 {
		Set tSC = ..Finish("OK", "")
		Do ..ReleaseAssociation(..Duplex)
		Quit tSC
	}
	Quit ..Finish("ERROR", "C-FIND status " _ tStatus)
}

Method Finish(pOutcome As %String, pMessage As %String) As %Status
{
	If ..Replied Quit $$$OK
	Set ..Replied = 1
	Set tResp = ##class(PacsDicom.Msg.CFindResponse).%New()
	Set tResp.Outcome = pOutcome, tResp.Message = pMessage
	Set tResp.MatchesJson = ..Collected
	Set tResp.MatchCount = ##class(%DynamicArray).%FromJSON(..Collected).%Size()
	Quit ..Reply(tResp)
}

Method OnAssociationRejected(pSourceConfigName As %String, pInput As EnsLib.DICOM.Notify.Rejected) As %Status
{
	Quit ..Finish("ERROR", "association rejected by " _ ..QueryTarget)
}

Method OnAssociationErrored(pSourceConfigName As %String, pInput As EnsLib.DICOM.Notify.Errored) As %Status
{
	Quit ..Finish("ERROR", $System.Status.GetErrorText(pInput.Status))
}

Method OnAssociationAborted(pSourceConfigName As %String, pInput As EnsLib.DICOM.Notify.Aborted) As %Status
{
	Quit ..Finish("ERROR", "association aborted")
}

Method OnAssociationReleased(pSourceConfigName As %String, pInput As EnsLib.DICOM.Notify.Released) As %Status
{
	Quit ..Finish("ERROR", "association released before the query finished")
}

Storage Default
{
<Data name="CFindDefaultData">
<Subscript>"CFind"</Subscript>
<Value name="1">
<Value>Duplex</Value>
</Value>
<Value name="2">
<Value>QueryTarget</Value>
</Value>
<Value name="3">
<Value>QueryPatientID</Value>
</Value>
<Value name="4">
<Value>QueryStudyDate</Value>
</Value>
<Value name="5">
<Value>QueryModality</Value>
</Value>
<Value name="6">
<Value>Collected</Value>
</Value>
<Value name="7">
<Value>Replied</Value>
</Value>
</Data>
<DefaultData>CFindDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
