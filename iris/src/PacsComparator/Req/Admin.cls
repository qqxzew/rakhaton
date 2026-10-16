/// Administration of the production (called by scripts/iris_setup.py).
Class PacsComparator.Req.Admin Extends %RegisteredObject
{

/// Starts PacsComparator.Production, or applies a changed definition when it already runs.
ClassMethod EnsureRunning() As %String
{
	Set sc = ##class(Ens.Director).GetProductionStatus(.name, .state)
	If $$$ISOK(sc), state = 1 {
		If name '= "PacsComparator.Production" Quit "other production running: " _ name
		// recompiled host classes only take effect in new jobs
		Set sc = ##class(Ens.Director).StopProduction(10, 1)
		If $$$ISERR(sc) Quit "stop failed: " _ $System.Status.GetErrorText(sc)
	}
	Set sc = ##class(Ens.Director).StartProduction("PacsComparator.Production")
	If $$$ISERR(sc) Quit "start failed: " _ $System.Status.GetErrorText(sc)
	Do ##class(Ens.Director).SetAutoStart("PacsComparator.Production")
	Quit "started"
}

ClassMethod SetCredential(id As %String, user As %String, password As %String) As %String
{
	Set sc = ##class(Ens.Config.Credentials).SetCredential(id, user, password, 1)
	Quit $Select($$$ISOK(sc): "ok", 1: $System.Status.GetErrorText(sc))
}

}
