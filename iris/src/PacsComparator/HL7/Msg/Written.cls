/// Written to the backend hook after a ServiceRequest from the RIS has been stored.
Class PacsComparator.HL7.Msg.Written Extends Ens.Request
{

Property PatientId As %String(MAXLEN = 80);

Property ResourceType As %String(MAXLEN = 40);

Property ResourceId As %String(MAXLEN = 80);

}
