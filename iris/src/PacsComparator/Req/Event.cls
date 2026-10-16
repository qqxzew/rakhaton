/// One state transition (or noteworthy event without transition) of a request.
Class PacsComparator.Req.Event Extends %Persistent
{

Property RequestId As %String(MAXLEN = 40);

Property Ts As %String(MAXLEN = 24);

/// system, coordinator or provider-sim
Property Actor As %String(MAXLEN = 120);

Property FromState As %String(MAXLEN = 30);

Property ToState As %String(MAXLEN = 30);

Property Note As %String(MAXLEN = 600);

Property SessionId As %String(MAXLEN = 30);

Index RequestIdx On RequestId;

}
