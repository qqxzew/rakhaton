Include Ensemble

/// Timer of the request loop: every CallInterval seconds it asks the lifecycle process to handle
/// the requests whose next action (reminder, voice escalation, human hand-over) is due.
Class PacsComparator.BS.Ticker Extends Ens.BusinessService
{

Parameter ADAPTER = "Ens.InboundAdapter";

Property TargetConfigName As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.BP.RequestLifecycle" ];

Parameter SETTINGS = "TargetConfigName:Basic";

Method OnProcessInput(pInput As %RegisteredObject, Output pOutput As %RegisteredObject) As %Status
{
	Set ids = ##class(PacsComparator.Req.Api).DueIds()
	For i = 1:1:$Length(ids, ",") {
		Set id = $Piece(ids, ",", i)
		If id = "" Continue
		Set e = ##class(PacsComparator.Msg.Event).%New()
		Set e.Action = "TICK", e.RequestId = id, e.Actor = "system"
		Set sc = ..SendRequestSync(..TargetConfigName, e, .r)
		If $$$ISERR(sc) {
			$$$LOGWARNING("TICK " _ id _ ": " _ $Extract($System.Status.GetErrorText(sc), 1, 300))
		}
	}
	Quit $$$OK
}

}
