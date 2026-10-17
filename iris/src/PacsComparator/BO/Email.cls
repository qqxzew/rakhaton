Include Ensemble

/// Email through the SMTP adapter (sandbox: Mailpit, host "mailpit" on the compose network).
Class PacsComparator.BO.Email Extends Ens.BusinessOperation
{

Parameter ADAPTER = "EnsLib.EMail.OutboundAdapter";

Parameter INVOCATION = "Queue";

Property Adapter As EnsLib.EMail.OutboundAdapter;

Property Sender As %String [ InitialExpression = "koordinator-mdt@motol.example" ];

Parameter SETTINGS = "Sender";

Method Send(pRequest As PacsComparator.Msg.Email, Output pResponse As PacsComparator.Msg.Ack) As %Status
{
	Set pResponse = ##class(PacsComparator.Msg.Ack).%New()
	Set mail = ##class(%Net.MailMessage).%New()
	Set mail.From = ..Sender
	Do mail.To.Insert(pRequest.To)
	Set mail.Subject = pRequest.Subject
	Set mail.Charset = "UTF-8"
	Do mail.Headers.SetAt("true", "X-Simulation")
	Do mail.Headers.SetAt(pRequest.RequestId, "X-Request-Id")
	Do mail.TextData.Write(pRequest.Body)
	Set tSC = ..Adapter.SendMail(mail)
	Set pResponse.Ok = $$$ISOK(tSC)
	Quit tSC
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="PacsComparator.Msg.Email">
    <Method>Send</Method>
  </MapItem>
</MapItems>
}

}
