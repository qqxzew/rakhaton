/// Applies the HL7 items of the production without a restart (called by scripts/iris_hl7.py).
Class PacsComparator.HL7.Admin Extends %RegisteredObject
{

ClassMethod Apply() As %String
{
	Set sc = ##class(Ens.Director).GetProductionStatus(.name, .state)
	If $$$ISERR(sc) || (state '= 1) Quit "production not running"
	If name '= "PacsComparator.Production" Quit "other production running: " _ name
	Set sc = ##class(Ens.Director).UpdateProduction(30)
	Quit $Select($$$ISOK(sc): "updated", 1: "update failed: " _ $System.Status.GetErrorText(sc))
}

/// Sets HookUrl of the backend hook item in the stored production definition (used for non-default backend ports).
ClassMethod SetHookUrl(url As %String) As %String
{
	Set prod = ##class(Ens.Config.Production).%OpenId("PacsComparator.Production")
	If '$IsObject(prod) Quit "production not found"
	Set item = ""
	For i = 1:1:prod.Items.Count() {
		If prod.Items.GetAt(i).Name = "PacsComparator.HL7.BO.BackendHook" Set item = prod.Items.GetAt(i)
	}
	If '$IsObject(item) Quit "item not found"
	Set found = 0
	For j = 1:1:item.Settings.Count() {
		Set s = item.Settings.GetAt(j)
		If s.Name = "HookUrl" Set s.Value = url, found = 1
	}
	If 'found {
		Set s = ##class(Ens.Config.Setting).%New()
		Set s.Target = "Host", s.Name = "HookUrl", s.Value = url
		Do item.Settings.Insert(s)
	}
	Set sc = prod.%Save()
	Quit $Select($$$ISOK(sc): "ok", 1: $System.Status.GetErrorText(sc))
}

}
