/// Email to a provider (sandbox: Mailpit).
Class PacsComparator.Msg.Email Extends Ens.Request
{

Property RequestId As %String(MAXLEN = 40);

Property To As %String(MAXLEN = 200);

Property Subject As %String(MAXLEN = 300);

Property Body As %String(MAXLEN = "");

}
