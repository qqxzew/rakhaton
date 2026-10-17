/// A message of the request: outgoing email or reminder, voice call script (with optional audio),
/// incoming reply or delivery. Everything here is simulated (hard rule 5).
Class PacsComparator.Req.Message Extends %Persistent
{

Property RequestId As %String(MAXLEN = 40);

Property Ts As %String(MAXLEN = 24);

/// email, reminder, voice_call, call_outcome, reply, delivery
Property Kind As %String(MAXLEN = 20);

/// out or in
Property Direction As %String(MAXLEN = 4);

/// email, phone, fhir
Property Channel As %String(MAXLEN = 10);

Property Subject As %String(MAXLEN = 300);

Property Body As %String(MAXLEN = "");

/// Reply class or call outcome
Property ReplyClass As %String(MAXLEN = 40);

/// Quote that justified the class
Property Quote As %String(MAXLEN = 600);

Property ParseMethod As %String(MAXLEN = 40);

Property Audio As %Stream.GlobalBinary;

Index RequestIdx On RequestId;

}
