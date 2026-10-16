/// The request loop of the PACS comparator as an IRIS Interoperability production.
/// Timer settings: TimerProfile "demo" makes every timer DemoSeconds long; "normal" uses the *AfterSeconds
/// settings (24 hours each). The demo "advance time" button moves a clock offset instead (Req.Api.AdvanceTime).
Class PacsComparator.Production Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="PacsComparator.Production" LogGeneralTraceEvents="false">
  <Description>Request loop: draft, approval, email, reminder, voice escalation, reply parsing, delivery verification, FHIR Task mirror</Description>
  <ActorPoolSize>1</ActorPoolSize>
  <Item Name="PacsComparator.BS.RequestIntake" Category="" ClassName="PacsComparator.BS.RequestIntake" PoolSize="0" Enabled="true" Foreground="false" Comment="Called by the Python backend through the native API" LogTraceEvents="true" Schedule="">
  </Item>
  <Item Name="PacsComparator.BS.Ticker" Category="" ClassName="PacsComparator.BS.Ticker" PoolSize="1" Enabled="true" Foreground="false" Comment="Starts reminders and escalations that are due" LogTraceEvents="false" Schedule="">
    <Setting Target="Adapter" Name="CallInterval">5</Setting>
  </Item>
  <Item Name="PacsComparator.BP.RequestLifecycle" Category="" ClassName="PacsComparator.BP.RequestLifecycle" PoolSize="1" Enabled="true" Foreground="false" Comment="State machine DETECTED ... VERIFIED" LogTraceEvents="true" Schedule="">
    <Setting Target="Host" Name="TimerProfile">normal</Setting>
    <Setting Target="Host" Name="ReminderAfterSeconds">86400</Setting>
    <Setting Target="Host" Name="VoiceAfterSeconds">86400</Setting>
    <Setting Target="Host" Name="HumanAfterSeconds">86400</Setting>
    <Setting Target="Host" Name="DemoSeconds">20</Setting>
    <Setting Target="Host" Name="LlmModel">gpt-6-luna-dz-eu</Setting>
    <Setting Target="Host" Name="LlmCredentials">PacsComparator.Llm</Setting>
  </Item>
  <Item Name="PacsComparator.BO.Email" Category="" ClassName="PacsComparator.BO.Email" PoolSize="1" Enabled="true" Foreground="false" Comment="SMTP to Mailpit (simulation)" LogTraceEvents="true" Schedule="">
    <Setting Target="Adapter" Name="SMTPServer">mailpit</Setting>
    <Setting Target="Adapter" Name="SMTPPort">1025</Setting>
  </Item>
  <Item Name="PacsComparator.BO.HospitalFhir" Category="" ClassName="PacsComparator.BO.HospitalFhir" PoolSize="1" Enabled="true" Foreground="false" Comment="Finds MHD deliveries and provider ImagingStudy (simulated hospitals)" LogTraceEvents="true" Schedule="">
    <Setting Target="Host" Name="MotolBase">http://localhost:52773/fhir/r4</Setting>
    <Setting Target="Host" Name="Credentials">PacsComparator.Iris</Setting>
  </Item>
  <Item Name="PacsComparator.BO.Voice" Category="" ClassName="PacsComparator.BO.Voice" PoolSize="1" Enabled="true" Foreground="false" Comment="Czech voice script, optional ElevenLabs TTS (simulation)" LogTraceEvents="true" Schedule="">
    <Setting Target="Host" Name="Credentials">PacsComparator.Voice</Setting>
  </Item>
  <Item Name="PacsComparator.BO.FhirWriter" Category="" ClassName="PacsComparator.BO.FhirWriter" PoolSize="1" Enabled="true" Foreground="false" Comment="PUT Task, Communication, AuditEvent to /fhir/r4" LogTraceEvents="true" Schedule="">
    <Setting Target="Host" Name="FhirBase">http://localhost:52773/fhir/r4</Setting>
    <Setting Target="Host" Name="Credentials">PacsComparator.Iris</Setting>
  </Item>
  <Item Name="PacsComparator.HL7.BS.Tcp" Category="HL7" ClassName="PacsComparator.HL7.BS.Tcp" PoolSize="1" Enabled="true" Foreground="false" Comment="HL7 v2 MLLP from the simulated RIS (port 4561 inside the container)" LogTraceEvents="true" Schedule="">
    <Setting Target="Adapter" Name="Port">4561</Setting>
    <Setting Target="Adapter" Name="StayConnected">-1</Setting>
    <Setting Target="Host" Name="MessageSchemaCategory">2.5</Setting>
    <Setting Target="Host" Name="TargetConfigNames">PacsComparator.HL7.BP.Route</Setting>
    <Setting Target="Host" Name="AckMode">Immediate</Setting>
  </Item>
  <Item Name="PacsComparator.HL7.BS.File" Category="HL7" ClassName="PacsComparator.HL7.BS.File" PoolSize="1" Enabled="true" Foreground="false" Comment="HL7 v2 file fallback from the simulated RIS (folder inside the container)" LogTraceEvents="true" Schedule="">
    <Setting Target="Adapter" Name="FilePath">/tmp/pacs-hl7/in/</Setting>
    <Setting Target="Adapter" Name="FileSpec">*.hl7</Setting>
    <Setting Target="Adapter" Name="ArchivePath">/tmp/pacs-hl7/done/</Setting>
    <Setting Target="Adapter" Name="WorkPath">/tmp/pacs-hl7/work/</Setting>
    <Setting Target="Adapter" Name="CallInterval">2</Setting>
    <Setting Target="Host" Name="MessageSchemaCategory">2.5</Setting>
    <Setting Target="Host" Name="TargetConfigNames">PacsComparator.HL7.BP.Route</Setting>
  </Item>
  <Item Name="PacsComparator.HL7.BP.Route" Category="HL7" ClassName="PacsComparator.HL7.BP.Route" PoolSize="1" Enabled="true" Foreground="false" Comment="ORM^O01 to ServiceRequest, ORU^R01 to DiagnosticReport, then the backend hook" LogTraceEvents="true" Schedule="">
    <Setting Target="Host" Name="FhirBase">http://localhost:52773/fhir/r4</Setting>
    <Setting Target="Host" Name="Credentials">PacsComparator.Iris</Setting>
  </Item>
  <Item Name="PacsComparator.HL7.BO.BackendHook" Category="HL7" ClassName="PacsComparator.HL7.BO.BackendHook" PoolSize="1" Enabled="true" Foreground="false" Comment="Tells the backend to re-check the cases of the patient (best effort)" LogTraceEvents="true" Schedule="">
    <Setting Target="Host" Name="HookUrl">http://host.docker.internal:8000/api/hooks/fhir-written</Setting>
  </Item>
</Production>
}

}
