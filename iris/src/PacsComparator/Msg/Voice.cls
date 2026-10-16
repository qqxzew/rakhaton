/// Voice escalation: the script never identifies the patient (hard rule 7).
Class PacsComparator.Msg.Voice Extends Ens.Request
{

Property RequestId As %String(MAXLEN = 40);

Property Phone As %String(MAXLEN = 60);

Property Script As %String(MAXLEN = "");

}
