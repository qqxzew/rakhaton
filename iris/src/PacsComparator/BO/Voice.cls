Include Ensemble

/// Voice escalation (simulated call, CLAUDE.md 10.6). Stores the Czech script as a message of the
/// request and, when an ElevenLabs credential exists (username = voice id, password = API key),
/// the synthesized mp3. Without it only the transcript exists (the UI then uses speechSynthesis).
Class PacsComparator.BO.Voice Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Property Credentials As %String(MAXLEN = 100) [ InitialExpression = "PacsComparator.Voice" ];

Parameter SETTINGS = "Credentials";

Method Call(pRequest As PacsComparator.Msg.Voice, Output pResponse As PacsComparator.Msg.Ack) As %Status
{
	Set pResponse = ##class(PacsComparator.Msg.Ack).%New()
	Set m = ##class(PacsComparator.Req.Message).%New()
	Set m.RequestId = pRequest.RequestId, m.Ts = ##class(PacsComparator.Req.Util).Now()
	Set m.Kind = "voice_call", m.Direction = "out", m.Channel = "phone"
	Set m.Subject = "Hlasová zpráva (simulovaný hovor)", m.Body = pRequest.Script
	Set m.ParseMethod = "transcript"
	Set sc = ##class(Ens.Config.Credentials).GetCredentialsObj(.cred, ..%ClassName(1), "Ens.Config.Credentials", ..Credentials)
	If $$$ISOK(sc) {
		Set b64 = ##class(PacsComparator.Req.Logic).Tts(pRequest.Script, cred.Username, cred.Password)
		If b64 '= "" {
			Do m.Audio.Write($System.Encryption.Base64Decode(b64))
			Set m.ParseMethod = "elevenlabs"
		}
	}
	Set tSC = m.%Save()
	Quit:$$$ISERR(tSC) tSC
	Set pResponse.MessageId = m.%Id()
	Set pResponse.Info = m.ParseMethod
	Quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="PacsComparator.Msg.Voice">
    <Method>Call</Method>
  </MapItem>
</MapItems>
}

}
