/// Test production for the DICOM C-FIND components (own namespace PACSDICOM, T087).
/// The operations point at the simulated PACS (Orthanc) through host.docker.internal.
/// To reuse the components in another production add: PacsDicom.BS.Api, PacsDicom.BP.CFind and one
/// PacsDicom.BO.CFind item per hospital (named "CFind.<AE>"), and run PacsDicom.Api.Configure() once.
Class PacsDicom.TestProduction Extends Ens.Production
{

Parameter SETTINGS = "StorageLocation:Basic";

Property StorageLocation As %String;

XData ProductionDefinition
{
<Production Name="PacsDicom.TestProduction" TestingEnabled="true" LogGeneralTraceEvents="false">
  <Description>Simulace PACS: DICOM C-FIND dotazy na Orthanc (FN Motol, NNH, Homolka, FNM)</Description>
  <ActorPoolSize>2</ActorPoolSize>
  <Setting Target="Production" Name="StorageLocation">/tmp/</Setting>
  <Item Name="PacsDicom.BS.Api" Category="" ClassName="PacsDicom.BS.Api" PoolSize="0" Enabled="true" Foreground="false" Comment="Entry point called from the backend" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="PacsDicom.BP.CFind" Category="" ClassName="PacsDicom.BP.CFind" PoolSize="2" Enabled="true" Foreground="false" Comment="C-FIND private session driver" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="CFind.MOTOL" Category="" ClassName="PacsDicom.BO.CFind" PoolSize="1" Enabled="true" Foreground="false" Comment="Simulace PACS FN Motol" LogTraceEvents="false" Schedule="">
    <Setting Target="Adapter" Name="IPAddress">host.docker.internal</Setting>
    <Setting Target="Adapter" Name="IPPort">4251</Setting>
    <Setting Target="Adapter" Name="LocalAET">WLCMP</Setting>
    <Setting Target="Adapter" Name="RemoteAET">MOTOL</Setting>
    <Setting Target="Host" Name="BusinessPartner">PacsDicom.BP.CFind</Setting>
  </Item>
  <Item Name="CFind.NNH" Category="" ClassName="PacsDicom.BO.CFind" PoolSize="1" Enabled="true" Foreground="false" Comment="Simulace PACS NNH" LogTraceEvents="false" Schedule="">
    <Setting Target="Adapter" Name="IPAddress">host.docker.internal</Setting>
    <Setting Target="Adapter" Name="IPPort">4252</Setting>
    <Setting Target="Adapter" Name="LocalAET">WLCMP</Setting>
    <Setting Target="Adapter" Name="RemoteAET">NNH</Setting>
    <Setting Target="Host" Name="BusinessPartner">PacsDicom.BP.CFind</Setting>
  </Item>
  <Item Name="CFind.HOMOLKA" Category="" ClassName="PacsDicom.BO.CFind" PoolSize="1" Enabled="true" Foreground="false" Comment="Simulace PACS Homolka" LogTraceEvents="false" Schedule="">
    <Setting Target="Adapter" Name="IPAddress">host.docker.internal</Setting>
    <Setting Target="Adapter" Name="IPPort">4253</Setting>
    <Setting Target="Adapter" Name="LocalAET">WLCMP</Setting>
    <Setting Target="Adapter" Name="RemoteAET">HOMOLKA</Setting>
    <Setting Target="Host" Name="BusinessPartner">PacsDicom.BP.CFind</Setting>
  </Item>
  <Item Name="CFind.FNM" Category="" ClassName="PacsDicom.BO.CFind" PoolSize="1" Enabled="true" Foreground="false" Comment="Simulace PACS FNM" LogTraceEvents="false" Schedule="">
    <Setting Target="Adapter" Name="IPAddress">host.docker.internal</Setting>
    <Setting Target="Adapter" Name="IPPort">4254</Setting>
    <Setting Target="Adapter" Name="LocalAET">WLCMP</Setting>
    <Setting Target="Adapter" Name="RemoteAET">FNM</Setting>
    <Setting Target="Host" Name="BusinessPartner">PacsDicom.BP.CFind</Setting>
  </Item>
</Production>
}

}
