/// Czech texts of the outbound messages. Minimum data only (hard rule 8): request id, study date,
/// modality, body region, accession reference if any, route, deadline, contact. No patient identifiers.
/// The voice script never identifies the patient (hard rule 7).
Class PacsComparator.Req.Templates Extends %RegisteredObject
{

ClassMethod RegionText(regions As %String) As %String
{
	Set out = ""
	For i = 1:1:$Length(regions, ",") {
		Set r = $Piece(regions, ",", i)
		If r = "" Continue
		Set t = $Case(r, "head": "hlava", "brain": "mozek", "neck": "krk", "chest": "hrudník", "abdomen": "břicho", "pelvis": "pánev", "spine": "páteř", "extremity": "končetina", "breast": "prs", "whole_body": "celé tělo", : r)
		Set out = out _ $Select(out = "": "", 1: ", ") _ t
	}
	Quit $Select(out = "": "neurčena", 1: out)
}

ClassMethod Subject(req As PacsComparator.Req.Request, reminder As %Boolean = 0) As %String
{
	Quit "[" _ req.RequestId _ "] " _ $Select(reminder: "Připomenutí: ", 1: "") _ "Žádost o zaslání obrazové dokumentace"
}

ClassMethod Body(req As PacsComparator.Req.Request, reminder As %Boolean = 0) As %String
{
	Set nl = $Char(13, 10)
	Set b = "Dobrý den," _ nl _ nl
	Set b = b _ $Select(reminder: "připomínáme naši dřívější žádost. ", 1: "")
	Set b = b _ "FN Motol, Radiodiagnostická klinika, žádá o zaslání obrazové dokumentace." _ nl _ nl
	Set b = b _ "Číslo žádosti: " _ req.RequestId _ nl
	Set b = b _ "Datum vyšetření: " _ req.TargetDate _ nl
	Set b = b _ "Modalita: " _ req.Modality _ nl
	Set b = b _ "Oblast: " _ ..RegionText(req.Regions) _ nl
	If req.AccessionRef '= "" Set b = b _ "Přístupové číslo: " _ req.AccessionRef _ nl
	Set b = b _ "Požadovaný způsob předání: " _ $Select(req.ProviderRoute '= "": req.ProviderRoute, 1: "ePACS") _ nl
	Set b = b _ "Termín: " _ req.Deadline _ nl
	Set b = b _ "Kontakt pro dotazy: radiologie@motol.example, +420 000 000 000" _ nl _ nl
	Set b = b _ "V odpovědi prosím uveďte číslo žádosti." _ nl _ "Děkujeme." _ nl _ nl
	Set b = b _ "[SIMULACE: zpráva míří do testovací schránky, ne na skutečné pracoviště.]" _ nl
	Quit b
}

ClassMethod VoiceScript(req As PacsComparator.Req.Request) As %String
{
	Quit "Dobrý den, tady automatický asistent Fakultní nemocnice v Motole, Radiodiagnostická klinika. Voláme ohledně žádosti číslo " _ req.RequestId _ " o zaslání obrazové dokumentace. Podrobnosti jsme zaslali e-mailem. Prosíme o zaslání přes " _ $Select(req.ProviderRoute '= "": req.ProviderRoute, 1: "ePACS") _ ". Děkujeme, na shledanou."
}

}
