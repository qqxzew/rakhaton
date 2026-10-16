Include Ensemble

/// Entry point of the request loop. The Python backend calls the class method Submit() through the
/// IRIS native API (the superserver port it already uses for IRIS SQL); Submit() starts a business
/// service call, so every request event is one Ensemble session visible in Visual Trace.
Class PacsComparator.BS.RequestIntake Extends Ens.BusinessService
{

Property TargetConfigName As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.BP.RequestLifecycle" ];

Parameter SETTINGS = "TargetConfigName:Basic";

Method OnProcessInput(pInput As PacsComparator.Msg.Event, Output pOutput As PacsComparator.Msg.Result) As %Status
{
	Set tSC = ..SendRequestSync(..TargetConfigName, pInput, .pOutput)
	If $IsObject(pOutput) Set pOutput.SessionId = ..%SessionId
	Quit tSC
}

/// Returns JSON: {"ok", "requestId", "state", "note", "sessionId"} or {"ok": false, "error", "sessionId"}.
ClassMethod Submit(action As %String, requestId As %String = "", payload As %String = "", actor As %String = "") As %String
{
	Set out = {"ok": false, "requestId": (requestId), "sessionId": ""}
	Try {
		Set tSC = ##class(Ens.Director).CreateBusinessService("PacsComparator.BS.RequestIntake", .svc)
		If $$$ISERR(tSC) {
			Set out.error = "Produkce neběží: " _ $Extract($System.Status.GetErrorText(tSC), 1, 300)
			Quit
		}
		Set msg = ##class(PacsComparator.Msg.Event).%New()
		Set msg.Action = action, msg.RequestId = requestId, msg.Payload = payload, msg.Actor = actor
		Set tSC = svc.ProcessInput(msg, .result)
		Set out.sessionId = svc.%SessionId
		If $$$ISERR(tSC) {
			Set out.error = $System.Status.GetOneStatusText(tSC)
			Quit
		}
		Set out.ok = 1, out.requestId = result.RequestId, out.state = result.State, out.note = result.Note
	} Catch ex {
		Set out.error = ex.DisplayString()
	}
	Quit out.%ToJSON()
}

}
