/// Small HTTP helper for the business operations (plain http inside the IRIS container).
Class PacsComparator.Req.Http Extends %RegisteredObject
{

/// Request prepared for an absolute http URL; `path` receives the path part (with a leading slash).
ClassMethod New(url As %String, credentials As %String = "", Output path As %String) As %Net.HttpRequest
{
	Set scheme = $Piece(url, "://", 1), rest = $Piece(url, "://", 2)
	Set hostport = $Piece(rest, "/", 1), path = "/" _ $Piece(rest, "/", 2, *)
	Set req = ##class(%Net.HttpRequest).%New()
	Set req.Server = $Piece(hostport, ":", 1)
	Set req.Port = $Select($Length(hostport, ":") > 1: $Piece(hostport, ":", 2), scheme = "https": 443, 1: 80)
	If credentials '= "" {
		Set sc = ##class(Ens.Config.Credentials).GetCredentialsObj(.cred, "PacsComparator.Req.Http", "Ens.Config.Credentials", credentials)
		If $$$ISOK(sc) {
			Set req.Username = cred.Username, req.Password = cred.Password
		}
	}
	Quit req
}

ClassMethod Origin(url As %String) As %String
{
	Quit $Piece(url, "://", 1) _ "://" _ $Piece($Piece(url, "://", 2), "/", 1)
}

/// Parsed JSON body of the last response, or "" when not JSON.
ClassMethod Body(req As %Net.HttpRequest) As %DynamicObject
{
	Try {
		Set obj = ##class(%DynamicAbstractObject).%FromJSON(req.HttpResponse.Data)
	} Catch {
		Set obj = ""
	}
	Quit obj
}

}
