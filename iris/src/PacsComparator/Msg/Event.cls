/// Event for the request lifecycle: DRAFT, APPROVE, TICK, REPLY, CALL_OUTCOME, DELIVERY, CANCEL, CLOSE.
Class PacsComparator.Msg.Event Extends Ens.Request
{

Property RequestId As %String(MAXLEN = 40);

Property Action As %String(MAXLEN = 30);

Property Actor As %String(MAXLEN = 120);

/// JSON object with action specific data
Property Payload As %String(MAXLEN = "");

}
