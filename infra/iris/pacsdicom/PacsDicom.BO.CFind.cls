Include EnsDICOM

/// Business operation: DICOM SCU towards one simulated PACS (Orthanc), via the IRIS DICOM adapter (T087).
/// One production item per hospital; name it "CFind.<AE title of the PACS>". Set the adapter settings
/// IPAddress, Port, LocalAET (our AE) and RemoteAET (the PACS AE) per item. The class is reusable in any
/// production: it only adds the study level C-FIND query builder to the standard DICOM operation, and is
/// driven by PacsDicom.BP.CFind through a private session.
Class PacsDicom.BO.CFind Extends EnsLib.DICOM.Operation.TCP
{

/// Study Root Query/Retrieve Information Model - FIND.
Parameter STUDYROOTFIND = "1.2.840.10008.5.1.4.1.2.2.1";

/// Builds a C-FIND-RQ document (study level) for the request.
ClassMethod BuildQuery(pRequest As PacsDicom.Msg.CFindRequest, pStorageLocation As %String = "", Output pDoc As EnsLib.DICOM.Document) As %Status
{
	Set tSC = $$$OK
	Try {
		Kill %objlasterror
		Set pDoc = ##class(EnsLib.DICOM.Document).%New(pStorageLocation)
		If '$IsObject(pDoc) Set tSC = $Get(%objlasterror, $$$ERROR(5001, "cannot create DICOM document")) Quit
		Set tSC = pDoc.SetValueAt($$$Str2MsgTyp("C-FIND-RQ"), "CommandSet.CommandField") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt(..#STUDYROOTFIND, "CommandSet.AffectedSOPClassUID") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt(0, "CommandSet.Priority") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt(258, "CommandSet.CommandDataSetType") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt("STUDY", "DataSet.(0008,0052)") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt(pRequest.PatientID, "DataSet.(0010,0020)") If $$$ISERR(tSC) Quit
		#; DA ranges ("YYYYMMDD-YYYYMMDD") have an odd length; DICOM requires a space pad
		Set tDate = pRequest.StudyDate
		If $Length(tDate)#2 Set tDate = tDate _ " "
		Set tSC = pDoc.SetValueAt(tDate, "DataSet.(0008,0020)") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt(pRequest.Modality, "DataSet.(0008,0061)") If $$$ISERR(tSC) Quit
		#; Return keys (sent empty)
		Set tSC = pDoc.SetValueAt("", "DataSet.(0008,0050)") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt("", "DataSet.(0008,1030)") If $$$ISERR(tSC) Quit
		Set tSC = pDoc.SetValueAt("", "DataSet.(0020,000D)") If $$$ISERR(tSC) Quit
	} Catch ex {
		Set tSC = ex.AsStatus()
	}
	Quit tSC
}

/// Reads one C-FIND-RSP identifier into a JSON object.
ClassMethod ReadMatch(pDoc As EnsLib.DICOM.Document) As %DynamicObject
{
	Set tObj = {}
	Set tObj.accession = pDoc.GetValueAt("DataSet.(0008,0050)")
	Set tObj.studyDate = pDoc.GetValueAt("DataSet.(0008,0020)")
	Set tObj.modalities = pDoc.GetValueAt("DataSet.(0008,0061)")
	Set tObj.description = pDoc.GetValueAt("DataSet.(0008,1030)")
	Set tObj.studyUid = pDoc.GetValueAt("DataSet.(0020,000D)")
	Set tObj.patientId = pDoc.GetValueAt("DataSet.(0010,0020)")
	Quit tObj
}

}
