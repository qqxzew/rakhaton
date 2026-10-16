/// Entry points used by backend/scripts/simulate_ris.py through the native API.
Class PacsComparator.HL7.Api Extends %RegisteredObject
{

/// Sends one HL7 v2 message over MLLP to the inbound service port inside this container and returns
/// the ACK text ("" on failure with the reason in `err`). Segments are separated by CR.
ClassMethod SendMllp(message As %String, port As %Integer = 4561) As %String
{
	Set dev = "|TCP|" _ port, ack = ""
	Try {
		Open dev:("127.0.0.1":port:"M"):10
		If '$Test Quit
		Use dev:(::"M")
		Write $Char(11) _ message _ $Char(28, 13)
		Write *-3
		For {
			Read line:10
			If '$Test Quit
			Set ack = ack _ line _ $Char(13)
			If line [ $Char(28) Quit
		}
		Close dev
	} Catch ex {
		Close dev
		Quit
	}
	If ack = "" Quit "ERROR: no ACK"
	Quit $Translate(ack, $Char(11, 28), "")
}

/// Writes one message file into the folder of the file service (FilePath setting).
ClassMethod DropFile(name As %String, message As %String, dir As %String = "/tmp/pacs-hl7/in/") As %String
{
	Do ##class(%File).CreateDirectoryChain(dir)
	Set stream = ##class(%Stream.FileCharacter).%New()
	Set stream.Filename = dir _ name
	Set stream.TranslateTable = "UTF8"
	Do stream.Write(message)
	Set sc = stream.%Save()
	Quit $Select($$$ISOK(sc): "ok", 1: $System.Status.GetErrorText(sc))
}

/// Counts for the check script: message headers of the HL7 components and the last session ids.
ClassMethod HeaderCount(since As %String = "") As %Integer
{
	&sql(SELECT COUNT(*) INTO :n FROM Ens.MessageHeader WHERE (SourceConfigName LIKE 'PacsComparator.HL7.%' OR TargetConfigName LIKE 'PacsComparator.HL7.%') AND TimeCreated >= :since)
	Quit +$Get(n)
}

}
