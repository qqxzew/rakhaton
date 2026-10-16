/// Call from outside IRIS (the Python adapter uses the Native API): one C-FIND, answer as JSON text (T087).
Class PacsDicom.Api Extends %RegisteredObject
{

/// Returns {"outcome":"OK|ERROR","message":"...","matches":[{accession,studyDate,modalities,...}]}.
ClassMethod CFind(pTarget As %String, pPatientID As %String, pStudyDate As %String = "", pModality As %String = "") As %String
{
	Set tResult = {"outcome":"ERROR", "message":"", "matches":[]}
	Try {
		Set tReq = ##class(PacsDicom.Msg.CFindRequest).%New()
		Set tReq.Target = pTarget, tReq.PatientID = pPatientID, tReq.StudyDate = pStudyDate, tReq.Modality = pModality
		Set tSC = ##class(Ens.Director).CreateBusinessService("PacsDicom.BS.Api", .tService)
		If $$$ISOK(tSC) Set tSC = tService.ProcessInput(tReq, .tResp)
		If $$$ISERR(tSC) {
			Set tResult.message = $System.Status.GetErrorText(tSC)
		} ElseIf '$IsObject(tResp) {
			Set tResult.message = "No response from the C-FIND process"
		} Else {
			Set tResult.outcome = tResp.Outcome, tResult.message = tResp.Message
			Set tResult.matches = ##class(%DynamicArray).%FromJSON(tResp.MatchesJson)
		}
	} Catch ex {
		Set tResult.message = ex.DisplayString()
	}
	Quit tResult.%ToJSON()
}

/// Adds the DICOM association contexts (our AE -> each PACS AE) and starts the test production.
ClassMethod Configure(pLocalAET As %String = "WLCMP", pRemoteAETs As %String = "MOTOL,NNH,HOMOLKA,FNM") As %Status
{
	Set tSC = $$$OK
	For i = 1:1:$Length(pRemoteAETs, ",") {
		Set tRemote = $Piece(pRemoteAETs, ",", i)
		If ##class(EnsLib.DICOM.Util.AssociationContext).AETExists(pLocalAET, tRemote) {
			Set tSC = ##class(EnsLib.DICOM.Util.AssociationContext).AETDelete(pLocalAET, tRemote)
			If $$$ISERR(tSC) Quit
		}
		Set tAC = ##class(EnsLib.DICOM.Util.AssociationContext).%New(pLocalAET, tRemote)
		Set tAC.Name = "PacsDicom " _ tRemote
		For tUID = "1.2.840.10008.5.1.4.1.2.2.1", "1.2.840.10008.1.1" {
			Set tPC = ##class(EnsLib.DICOM.Util.PresentationContext).%New(tUID)
			Do tPC.TransferSyntaxes.Insert("1.2.840.10008.1.2")
			Do tAC.PresentationContexts.Insert(tPC)
		}
		Set tSC = tAC.%Save()
		If $$$ISERR(tSC) Quit
	}
	Quit tSC
}

}
