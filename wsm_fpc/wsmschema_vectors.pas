program wsmschema_vectors;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Self-check for the wsmschema unit.

  Every expected line below was printed by the repository's Python validator -
  jsonschema.Draft202012Validator(schema, format_checker=FormatChecker()) with
  cli.py's sort key and location format - not written by hand. Regenerate with
  the command recorded in FPC-SCHEMA-SLICE.md.

  The program validates each embedded document against the schema file from the
  repository tree, compares the rendered errors line by line and halts 1 on any
  difference. Usage:

    ./wsmschema-vectors [repo-root]

  Without an argument the root is the parent of the directory holding the
  executable, which is where `make` builds it. }

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, fpjson, jsonparser, wsmschema;

type
  TVector = record
    Id: string;
    SchemaRelPath: string;
    Note: string;
    Document: string;
    Expected: array of string;
  end;

function MakeVector(const Id, SchemaRelPath, Note, Document: string;
  const Expected: array of string): TVector;
var
  I: Integer;
begin
  Result.Id := Id;
  Result.SchemaRelPath := SchemaRelPath;
  Result.Note := Note;
  Result.Document := Document;
  SetLength(Result.Expected, Length(Expected));
  for I := 0 to High(Expected) do
    Result.Expected[I] := Expected[I];
end;

var
  Vectors: array of TVector;

procedure Add(const V: TVector);
begin
  SetLength(Vectors, Length(Vectors) + 1);
  Vectors[High(Vectors)] := V;
end;

function LoadJsonFile(const Path: string): TJSONData;
var
  Stream: TFileStream;
  Parser: TJSONParser;
begin
  Stream := TFileStream.Create(Path, fmOpenRead or fmShareDenyWrite);
  try
    Parser := TJSONParser.Create(Stream, True);
    try
      Result := Parser.Parse;
    finally
      Parser.Free;
    end;
  finally
    Stream.Free;
  end;
end;

function ParseJsonText(const Text: string): TJSONData;
var
  Parser: TJSONParser;
  Stream: TStringStream;
begin
  Stream := TStringStream.Create(Text);
  try
    Parser := TJSONParser.Create(Stream, True);
    try
      Result := Parser.Parse;
    finally
      Parser.Free;
    end;
  finally
    Stream.Free;
  end;
end;

function JoinLines(const Lines: array of string): string;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to High(Lines) do
  begin
    if I > 0 then
      Result := Result + LineEnding;
    Result := Result + Lines[I];
  end;
end;

function CheckVector(const Root: string; const V: TVector): Boolean;
var
  Schema, Document: TJSONData;
  Got: string;
  Want: string;
begin
  Result := False;
  try
    Schema := LoadJsonFile(IncludeTrailingPathDelimiter(Root) + V.SchemaRelPath);
    try
      Document := ParseJsonText(V.Document);
      try
        Got := RenderErrors(ValidateDocument(Schema, Document));
      finally
        Document.Free;
      end;
    finally
      Schema.Free;
    end;
    Want := JoinLines(V.Expected);
    Result := Got = Want;
    if Result then
      WriteLn('PASS  ', V.Id)
    else
    begin
      WriteLn('FAIL  ', V.Id, '  (', V.Note, ')');
      WriteLn('  expected:');
      WriteLn(Want);
      WriteLn('  actual:');
      WriteLn(Got);
    end;
  except
    on E: Exception do
    begin
      WriteLn('FAIL  ', V.Id, '  (', E.ClassName, ': ', E.Message, ')');
      Result := False;
    end;
  end;
end;

procedure BuildVectors;
begin
  Add(MakeVector(
    'valid-hardware-report',
    'schemas/hardware-report.schema.json',
    'Minimal hardware-report document that the Python validator accepts.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mot' +
    'herboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"funct' +
    'ional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obser' +
    'ved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    []));
  Add(MakeVector(
    'valid-hardware-report-1.0.0',
    'schemas/hardware-report-1.0.0.schema.json',
    'Minimal hardware-report-1.0.0 document that the Python validator accepts.',
    '{"schema_version":"1.0.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-read-only","sourc' +
    'e_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered","driver":{"status":"bo' +
    'und"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirm' +
    'ed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]},{"device_id":"dev-1","category":"motherboard","bus":"pci","discovery' +
    '_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"ki' +
    'nd":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":{"profile":"s' +
    'trict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    []));
  Add(MakeVector(
    'valid-release-info',
    'schemas/release-info.schema.json',
    'Minimal release-info document that the Python validator accepts.',
    '{"schema":"wsm-release-info/1","release_id":"wsm-desktop-preview","version":"0.1.0-rc4","display_name":"WSM Desktop preview","status":"pre-release","date":"2026' +
    '-11-26","scope":["read-only hardware evidence report"],"excluded":["no installer APPLY"],"requirements":{"python":">=3.10"},"artifacts":["wsm-desktop-0.1.0-rc4-' +
    'source.tar.gz"]}',
    []));
  Add(MakeVector(
    'valid-hardware-classification',
    'schemas/hardware-classification.schema.json',
    'Minimal hardware-classification document that the Python validator accepts.',
    '{"schema":"wsm-hardware-classification/2","subsystems":[{"subsystem":"cpu","level":"unknown","devices":["dev-0"],"reasons":["dev-0: no driver candidate"],"cover' +
    'age":"device-records-present","observation":"device-records-present","evidence_states":["no-driver-candidate"],"functional_tests":[],"device_evidence":[]}],"cou' +
    'nts":{"certified":0,"known":0,"unknown":1},"decision_policy":"docs/INSTALL-CAPABILITY-MATRIX.md","note":"Diagnostic summary only; it authorizes nothing and pick' +
    's no scenario."}',
    []));
  Add(MakeVector(
    'valid-profile-evidence',
    'schemas/profile-evidence.schema.json',
    'Minimal profile-evidence document that the Python validator accepts.',
    '{"schema":"wsm-profile-evidence/2","profile":{"vendor":"Gigabyte","model":"GA-H170-Gaming 3","slug":"gigabyte/ga-h170-gaming3"},"report_id":"замінити на report_' +
    'id зі звіту wsm-hwcheck","report_schema_version":"1.1.0","isa_level":"unknown","verified_on":"2026-11-26","verified_by":"автори проєкту","verified_functions":[{' +
    '"name":"graphics","status":"not-assessed","note":"що саме перевіряли"},{"name":"storage","status":"not-assessed"},{"name":"network","status":"not-assessed"},{"n' +
    'ame":"audio","status":"not-assessed"}],"known_limitations":["кожне обмеження окремим рядком"],"not_assessed":["suspend/resume","що ще не перевірено"],"artifacts' +
    '":[{"kind":"wsm-hwcheck-report","path":"artifacts/wsm-hwcheck-report.json","sha256":"0000000000000000000000000000000000000000000000000000000000000000","note":"з' +
    'амінити на точні байти реального wsm-hwcheck report"}],"profile_source":{"path":"profile.scm","sha256":"00000000000000000000000000000000000000000000000000000000' +
    '00000000"}}',
    []));
  Add(MakeVector(
    'valid-driver-profile',
    'drivers/schema/profile.schema.json',
    'Minimal driver-profile document that the Python validator accepts.',
    '{"schema_version":"1.2.0","profile_id":"minimal-profile","profile_class":"free","profile_status":"draft","enabled_by_default":false,"base_profile":null,"target"' +
    ':{"target_id":"h170-gaming-3-owner-reference","board_vendor":"Vendor","board_model":"Model","firmware_vendor":"Vendor","firmware_version":"F1","boot_mode":"uefi' +
    '","evidence_source":"https://example.invalid/profile","evidence_date":"2026-09-02"},"source":{"repository":"juv4uk/wsm-desktop","source_commit":null,"channel_lo' +
    'ck_file":"channels.lock.scm","channel_revisions":[{"name":"guix","url":"https://git.guix.gnu.org/guix.git","commit":"4e5195be20d9b124df8a8bb69213412236e4668e"}]' +
    ',"channel_authentication_evidence":"not-evaluated","notes":"minimal"},"kernel":{"package_candidate":null,"version":null,"configuration_status":"not-assessed","n' +
    'otes":"minimal"},"unobserved_device_classes":[],"devices":[{"device_id":"board-0","device_class":"platform","model":"Model","evidence_class":"windows-observed",' +
    '"observed_bdf":null,"pci_ids":[],"driver_candidates":[],"firmware":{"requirement":"unknown","package_candidates":[],"package_resolution":"not-assessed","live_ro' +
    'otfs":"not-assessed","initrd":"not-assessed","installed_rootfs":"not-assessed","runtime_load":"not-assessed","redistribution":"unknown","evidence":[]},"function' +
    'al_validation":{"status":"not-run","environment":"none","evidence":[]},"notes":["minimal"],"identity_evidence":[]}],"policy":{"nonfree_components_included":fals' +
    'e,"automatic_firmware_updates":false,"host_disk_writes":false,"unknown_must_remain_unknown":true}}',
    []));
  Add(MakeVector(
    'type',
    'schemas/hardware-report.schema.json',
    'device_id is an integer where a string is required.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":42,"category":"cpu","bus":"pci","discovery_status":"discovered","dr' +
    'iver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","c' +
    'onfidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP' +
    '-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherbo' +
    'ard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional' +
    '_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}' +
    ']}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.device_id: 42 is not of type ''string''']));
  Add(MakeVector(
    'type-list',
    'drivers/schema/profile.schema.json',
    'type as a list: source_commit must be string or null, not an integer.',
    '{"schema_version":"1.2.0","profile_id":"minimal-profile","profile_class":"free","profile_status":"draft","enabled_by_default":false,"base_profile":null,"target"' +
    ':{"target_id":"h170-gaming-3-owner-reference","board_vendor":"Vendor","board_model":"Model","firmware_vendor":"Vendor","firmware_version":"F1","boot_mode":"uefi' +
    '","evidence_source":"https://example.invalid/profile","evidence_date":"2026-09-02"},"source":{"repository":"juv4uk/wsm-desktop","source_commit":5,"channel_lock_' +
    'file":"channels.lock.scm","channel_revisions":[{"name":"guix","url":"https://git.guix.gnu.org/guix.git","commit":"4e5195be20d9b124df8a8bb69213412236e4668e"}],"c' +
    'hannel_authentication_evidence":"not-evaluated","notes":"minimal"},"kernel":{"package_candidate":null,"version":null,"configuration_status":"not-assessed","note' +
    's":"minimal"},"unobserved_device_classes":[],"devices":[{"device_id":"board-0","device_class":"platform","model":"Model","evidence_class":"windows-observed","ob' +
    'served_bdf":null,"pci_ids":[],"driver_candidates":[],"firmware":{"requirement":"unknown","package_candidates":[],"package_resolution":"not-assessed","live_rootf' +
    's":"not-assessed","initrd":"not-assessed","installed_rootfs":"not-assessed","runtime_load":"not-assessed","redistribution":"unknown","evidence":[]},"functional_' +
    'validation":{"status":"not-run","environment":"none","evidence":[]},"notes":["minimal"],"identity_evidence":[]}],"policy":{"nonfree_components_included":false,"' +
    'automatic_firmware_updates":false,"host_disk_writes":false,"unknown_must_remain_unknown":true}}',
    ['source.source_commit: 5 is not of type ''string'', ''null''']));
  Add(MakeVector(
    'enum',
    'schemas/hardware-report.schema.json',
    'category value outside the closed vocabulary.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"gpu-card","bus":"pci","discovery_status":"disco' +
    'vered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-obser' +
    'vation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"conn' +
    'ector":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category"' +
    ':"motherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"' +
    'functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"' +
    'observed"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.category: ''gpu-card'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']']));
  Add(MakeVector(
    'const',
    'schemas/hardware-report.schema.json',
    'schema_version pinned by const.',
    '{"schema_version":"9.9.9","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mot' +
    'herboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"funct' +
    'ional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obser' +
    'ved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['schema_version: ''1.1.0'' was expected']));
  Add(MakeVector(
    'const-bool',
    'schemas/hardware-report.schema.json',
    'privacy.network_upload_performed is const false.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mot' +
    'herboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"funct' +
    'ional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obser' +
    'ved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":true,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['privacy.network_upload_performed: False was expected']));
  Add(MakeVector(
    'pattern',
    'schemas/hardware-report.schema.json',
    'report_id must match ^[A-Za-z0-9_-]+$; the length is legal.',
    '{"schema_version":"1.1.0","report_id":"bad report id!!!!","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.0"' +
    ',"boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivil' +
    'eged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered",' +
    '"driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation"' +
    ',"confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":' +
    '"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mothe' +
    'rboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functio' +
    'nal_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observe' +
    'd"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['report_id: ''bad report id!!!!'' does not match ''^[A-Za-z0-9_-]+$''']));
  Add(MakeVector(
    'pattern-apostrophe',
    'schemas/hardware-report.schema.json',
    'Python repr picks double quotes for a string holding an apostrophe.',
    '{"schema_version":"1.1.0","report_id":"owner''s board report","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.1' +
    '2.0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpr' +
    'ivileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discover' +
    'ed","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observat' +
    'ion","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connect' +
    'or":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"m' +
    'otherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"fun' +
    'ctional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obs' +
    'erved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['report_id: "owner''s board report" does not match ''^[A-Za-z0-9_-]+$''']));
  Add(MakeVector(
    'minLength',
    'schemas/hardware-report.schema.json',
    'evidence summary must not be empty: minLength 1 has its own message.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":""}],"criticality":["input"],"display":{"connector":"DP-1"' +
    ',"refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard' +
    '","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_te' +
    'sts":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}]' +
    ',"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.evidence.0.summary: '''' should be non-empty']));
  Add(MakeVector(
    'maxLength',
    'schemas/hardware-report.schema.json',
    'report_id longer than 80 characters (pattern still matches).',
    '{"schema_version":"1.1.0","report_id":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","collected_at":"2026-11-26T00:00:00Z",' +
    '"environment":{"architecture":"x86_64","kernel_release":"6.12.0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"col' +
    'lectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-' +
    '0","category":"cpu","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-neede' +
    'd"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summa' +
    'ry":"observed"}],"criticality":["input"],"display":{"connector":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":51211019' +
    '0592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"req' +
    'uirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/' +
    'cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifie' +
    'rs_included":false,"network_requests_performed":false}}',
    ['report_id: ''xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'' is too long']));
  Add(MakeVector(
    'minimum',
    'schemas/hardware-report.schema.json',
    'cpu.logical_processors below minimum 1.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":0},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mot' +
    'herboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"funct' +
    'ional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obser' +
    'ved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.cpu.logical_processors: 0 is less than the minimum of 1']));
  Add(MakeVector(
    'exclusiveMinimum',
    'schemas/hardware-report.schema.json',
    'display.refresh_rate_hz must be strictly greater than 0.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":0},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"moth' +
    'erboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functi' +
    'onal_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observ' +
    'ed"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.display.refresh_rate_hz: 0 is less than or equal to the minimum of 0']));
  Add(MakeVector(
    'float-exclusiveMinimum',
    'schemas/hardware-report.schema.json',
    'Negative float instance: the message carries Python float repr.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":-0.5},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"m' +
    'otherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"fun' +
    'ctional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obs' +
    'erved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.display.refresh_rate_hz: -0.5 is less than or equal to the minimum of 0']));
  Add(MakeVector(
    'float-integral',
    'schemas/hardware-report.schema.json',
    '0.0 keeps its fraction in repr: "0.0", not "0".',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":0.0},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mo' +
    'therboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"func' +
    'tional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obse' +
    'rved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.display.refresh_rate_hz: 0.0 is less than or equal to the minimum of 0']));
  Add(MakeVector(
    'required',
    'schemas/hardware-report.schema.json',
    'device without the required driver key.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed",' +
    '"source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP-1","refresh_rate_hz":6' +
    '0},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard","bus":"pci","disco' +
    'very_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[' +
    '{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":{"profile' +
    '":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0: ''driver'' is a required property']));
  Add(MakeVector(
    'additionalProperties',
    'schemas/hardware-report.schema.json',
    'unknown key in a device object (additionalProperties: false).',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"},"unknown_field":1},{"device_id":"dev-' +
    '1","category":"motherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"n' +
    'ot-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z' +
    '","summary":"observed"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_perform' +
    'ed":false}}',
    ['devices.0: Additional properties are not allowed (''unknown_field'' was unexpected)']));
  Add(MakeVector(
    'additionalProperties-schema',
    'schemas/release-info.schema.json',
    'additionalProperties as a schema: requirements entries must be non-empty.',
    '{"schema":"wsm-release-info/1","release_id":"wsm-desktop-preview","version":"0.1.0-rc4","display_name":"WSM Desktop preview","status":"pre-release","date":"2026' +
    '-11-26","scope":["read-only hardware evidence report"],"excluded":["no installer APPLY"],"requirements":{"python":">=3.10","extra_requirement":""},"artifacts":[' +
    '"wsm-desktop-0.1.0-rc4-source.tar.gz"]}',
    ['requirements.extra_requirement: '''' should be non-empty']));
  Add(MakeVector(
    'items',
    'schemas/hardware-report.schema.json',
    'criticality array element outside its enum: the error path carries the index.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input","not-a-criticality"],"' +
    'display":{"connector":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"de' +
    'v-1","category":"motherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":' +
    '"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:0' +
    '0Z","summary":"observed"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_perfo' +
    'rmed":false}}',
    ['devices.0.criticality.1: ''not-a-criticality'' is not one of [''boot-path'', ''storage-install-target'', ''primary-display'', ''network-installation'', ''input'' +
     '', ''audio'', ''suspend-resume'', ''optional-peripheral'']']));
  Add(MakeVector(
    'minItems',
    'schemas/hardware-classification.schema.json',
    'subsystems must contain at least one entry.',
    '{"schema":"wsm-hardware-classification/2","subsystems":[],"counts":{"certified":0,"known":0,"unknown":1},"decision_policy":"docs/INSTALL-CAPABILITY-MATRIX.md","' +
    'note":"Diagnostic summary only; it authorizes nothing and picks no scenario."}',
    ['subsystems: [] should be non-empty']));
  Add(MakeVector(
    'uniqueItems',
    'schemas/hardware-report.schema.json',
    'duplicate criticality entry.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input","input"],"display":{"c' +
    'onnector":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","catego' +
    'ry":"motherboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"' +
    '},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary' +
    '":"observed"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}' +
    '}',
    ['devices.0.criticality: [''input'', ''input''] has non-unique elements']));
  Add(MakeVector(
    'format-date-time',
    'schemas/hardware-report.schema.json',
    'collected_at must be an RFC 3339 date-time.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-28","environment":{"architecture":"x86_64","kernel_release":"6.12.0","boot_m' +
    'ode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-rea' +
    'd-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered","driver"' +
    ':{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confid' +
    'ence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP-1","' +
    'refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard",' +
    '"bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_test' +
    's":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"' +
    'privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['collected_at: ''2026-11-28'' is not a ''date-time''']));
  Add(MakeVector(
    'format-date',
    'schemas/hardware-report.schema.json',
    'bios_date must be an RFC 3339 full-date.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"28.11.2026"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observatio' +
    'n","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector' +
    '":"DP-1","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"mot' +
    'herboard","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"funct' +
    'ional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"obser' +
    'ved"}]}],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['environment.platform.bios_date: ''28.11.2026'' is not a ''date''']));
  Add(MakeVector(
    'format-uri',
    'schemas/hardware-report.schema.json',
    'collector source_url must be a URI.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"not a uri"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered","driver":{"status":"bo' +
    'und"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirm' +
    'ed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP-1","refresh_rate_h' +
    'z":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard","bus":"pci","d' +
    'iscovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidenc' +
    'e":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":{"pro' +
    'file":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['collectors.0.source_url: ''not a uri'' is not a ''uri''']));
  Add(MakeVector(
    'ref',
    'schemas/hardware-report.schema.json',
    'Error inside $defs/evidence, reached through $ref from devices.items.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.' +
    '0","boot_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unpriv' +
    'ileged-read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered' +
    '","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"guess","confide' +
    'nce":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP-1","r' +
    'efresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard","' +
    'bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests' +
    '":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"p' +
    'rivacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.evidence.0.kind: ''guess'' is not one of [''live-observation'', ''kernel-log'', ''database-record'', ''functional-test'', ''manual-review'', ''user-re' +
     'ported'']']));
  Add(MakeVector(
    'ref-driver',
    'drivers/schema/profile.schema.json',
    'Error inside $defs/device reached through $ref from devices.items.',
    '{"schema_version":"1.2.0","profile_id":"minimal-profile","profile_class":"free","profile_status":"draft","enabled_by_default":false,"base_profile":null,"target"' +
    ':{"target_id":"h170-gaming-3-owner-reference","board_vendor":"Vendor","board_model":"Model","firmware_vendor":"Vendor","firmware_version":"F1","boot_mode":"uefi' +
    '","evidence_source":"https://example.invalid/profile","evidence_date":"2026-09-02"},"source":{"repository":"juv4uk/wsm-desktop","source_commit":null,"channel_lo' +
    'ck_file":"channels.lock.scm","channel_revisions":[{"name":"guix","url":"https://git.guix.gnu.org/guix.git","commit":"4e5195be20d9b124df8a8bb69213412236e4668e"}]' +
    ',"channel_authentication_evidence":"not-evaluated","notes":"minimal"},"kernel":{"package_candidate":null,"version":null,"configuration_status":"not-assessed","n' +
    'otes":"minimal"},"unobserved_device_classes":[],"devices":[{"device_id":"board-0","device_class":"not-a-class","model":"Model","evidence_class":"windows-observe' +
    'd","observed_bdf":null,"pci_ids":[],"driver_candidates":[],"firmware":{"requirement":"unknown","package_candidates":[],"package_resolution":"not-assessed","live' +
    '_rootfs":"not-assessed","initrd":"not-assessed","installed_rootfs":"not-assessed","runtime_load":"not-assessed","redistribution":"unknown","evidence":[]},"funct' +
    'ional_validation":{"status":"not-run","environment":"none","evidence":[]},"notes":["minimal"],"identity_evidence":[]}],"policy":{"nonfree_components_included":f' +
    'alse,"automatic_firmware_updates":false,"host_disk_writes":false,"unknown_must_remain_unknown":true}}',
    ['devices.0.device_class: ''not-a-class'' is not one of [''platform'', ''cpu'', ''graphics'', ''network'', ''nvme-storage'', ''sata-storage'', ''audio'', ''wifi''' +
     ', ''bluetooth'', ''other'']']));
  Add(MakeVector(
    'properties',
    'schemas/hardware-report.schema.json',
    'Nested property error proves recursion through properties.',
    '{"schema_version":"1.1.0","report_id":"fixture-report-0001","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":5,"kernel_release":"6.12.0","boo' +
    't_mode":"uefi","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-' +
    'read-only","source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered","driv' +
    'er":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","con' +
    'fidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP-1' +
    '","refresh_rate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboar' +
    'd","bus":"pci","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_t' +
    'ests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}' +
    '],"privacy":{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['environment.architecture: 5 is not of type ''string''']));
  Add(MakeVector(
    'root-not-object',
    'schemas/hardware-report.schema.json',
    'Root of the document is an array: the only error sits at $.',
    '[]',
    ['$: [] is not of type ''object''']));
  Add(MakeVector(
    'utf8-minLength',
    'schemas/release-info.schema.json',
    'Two Cyrillic code points, four UTF-8 bytes: minLength counts code points.',
    '{"schema":"wsm-release-info/1","release_id":"wsm-desktop-preview","version":"0.1.0-rc4","display_name":"її","status":"pre-release","date":"2026-11-26","scope":[' +
    '"read-only hardware evidence report"],"excluded":["no installer APPLY"],"requirements":{"python":">=3.10"},"artifacts":["wsm-desktop-0.1.0-rc4-source.tar.gz"]}',
    ['display_name: ''її'' is too short']));
  Add(MakeVector(
    'ordering-two-keywords-one-path',
    'schemas/hardware-report.schema.json',
    'minLength and pattern both fail on report_id; minLength is declared first.',
    '{"schema_version":"1.1.0","report_id":"","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.0","boot_mode":"uef' +
    'i","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-read-only","' +
    'source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered","driver":{"status' +
    '":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"co' +
    'nfirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}],"criticality":["input"],"display":{"connector":"DP-1","refresh_r' +
    'ate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"motherboard","bus":"pc' +
    'i","discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"ev' +
    'idence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":' +
    '{"profile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['report_id: '''' is too short',
     'report_id: '''' does not match ''^[A-Za-z0-9_-]+$''']));
  Add(MakeVector(
    'ordering-multi',
    'schemas/hardware-report.schema.json',
    'Five errors across five paths: shows the sort key and the tie order.',
    '{"schema_version":"0.0.0","report_id":"","collected_at":"2026-11-26T00:00:00Z","environment":{"architecture":"x86_64","kernel_release":"6.12.0","boot_mode":"uef' +
    'i","virtualization":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-read-only","' +
    'source_url":"https://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"cpu","bus":"pci","discovery_status":"discovered","driver":{"status' +
    '":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"co' +
    'nfirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":""}],"criticality":["input","input"],"display":{"connector":"DP-1","refresh_r' +
    'ate_hz":60},"cpu":{"logical_processors":8},"storage":{"capacity_bytes":512110190592,"transport":"nvme"}},{"device_id":"dev-1","category":"nonsense","bus":"pci",' +
    '"discovery_status":"discovered","driver":{"status":"bound"},"firmware":{"requirement":"not-required","runtime_status":"not-needed"},"functional_tests":[],"evide' +
    'nce":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":{"p' +
    'rofile":"strict-local","network_upload_performed":false,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['devices.0.criticality: [''input'', ''input''] has non-unique elements',
     'devices.0.evidence.0.summary: '''' should be non-empty',
     'devices.1.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'report_id: '''' is too short',
     'report_id: '''' does not match ''^[A-Za-z0-9_-]+$''',
     'schema_version: ''1.1.0'' was expected']));
  Add(MakeVector(
    'many-errors',
    'schemas/hardware-report.schema.json',
    'More than 20 errors: cli.py prints the first 20 and one omission line.',
    '{"schema_version":"1.1.0","report_id":"","collected_at":"today","environment":{"architecture":"x86_64","kernel_release":"6.12.0","boot_mode":"uefi","virtualizat' +
    'ion":"none-detected","platform":{"bios_date":"2026-09-02"}},"collectors":[{"name":"wsm-sysfs","available":true,"scope":"unprivileged-read-only","source_url":"ht' +
    'tps://example.invalid/collector"}],"devices":[{"device_id":"dev-0","category":"nonsense","bus":"pci","discovery_status":"discovered","functional_tests":[],"evid' +
    'ence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]},{"device_id":' +
    '"dev-1","category":"nonsense","bus":"pci","discovery_status":"discovered","functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed",' +
    '"source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]},{"device_id":"dev-2","category":"nonsense","bus":"pci","discovery_status' +
    '":"discovered","functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:' +
    '00Z","summary":"observed"}]},{"device_id":"dev-3","category":"nonsense","bus":"pci","discovery_status":"discovered","functional_tests":[],"evidence":[{"kind":"l' +
    'ive-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]},{"device_id":"dev-4","category' +
    '":"nonsense","bus":"pci","discovery_status":"discovered","functional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:' +
    '/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]},{"device_id":"dev-5","category":"nonsense","bus":"pci","discovery_status":"discovered","f' +
    'unctional_tests":[],"evidence":[{"kind":"live-observation","confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"o' +
    'bserved"}]},{"device_id":"dev-6","category":"nonsense","bus":"pci","discovery_status":"discovered","functional_tests":[],"evidence":[{"kind":"live-observation",' +
    '"confidence":"confirmed","source":"procfs:/cpuinfo","observed_at":"2026-11-26T00:00:00Z","summary":"observed"}]}],"privacy":{"profile":"strict-local","network_u' +
    'pload_performed":true,"sensitive_identifiers_included":false,"network_requests_performed":false}}',
    ['collected_at: ''today'' is not a ''date-time''',
     'devices.0: ''driver'' is a required property',
     'devices.0: ''firmware'' is a required property',
     'devices.0.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'devices.1: ''driver'' is a required property',
     'devices.1: ''firmware'' is a required property',
     'devices.1.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'devices.2: ''driver'' is a required property',
     'devices.2: ''firmware'' is a required property',
     'devices.2.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'devices.3: ''driver'' is a required property',
     'devices.3: ''firmware'' is a required property',
     'devices.3.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'devices.4: ''driver'' is a required property',
     'devices.4: ''firmware'' is a required property',
     'devices.4.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'devices.5: ''driver'' is a required property',
     'devices.5: ''firmware'' is a required property',
     'devices.5.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'devices.6: ''driver'' is a required property',
     'devices.6: ''firmware'' is a required property',
     'devices.6.category: ''nonsense'' is not one of [''cpu'', ''motherboard'', ''memory'', ''storage-controller'', ''storage-device'', ''network'', ''gpu'', ''displa' +
     'y'', ''audio'', ''input'', ''bluetooth'', ''usb-controller'', ''camera'', ''other'']',
     'privacy.network_upload_performed: False was expected',
     'report_id: '''' is too short',
     'report_id: '''' does not match ''^[A-Za-z0-9_-]+$''']));
end;

var
  Root: string;
  I, Failures: Integer;
begin
  if ParamCount >= 1 then
    Root := ParamStr(1)
  else
    Root := ExtractFileDir(ExtractFileDir(ExpandFileName(ParamStr(0))));

  BuildVectors;

  Failures := 0;
  for I := 0 to High(Vectors) do
    if not CheckVector(Root, Vectors[I]) then
      Inc(Failures);

  WriteLn;
  WriteLn(Length(Vectors), ' vector(s), ', Failures, ' difference(s)');
  if Failures = 0 then
  begin
    WriteLn('PASS: every vector matches the Python validator');
    Halt(0);
  end;
  WriteLn('FAIL: ', Failures, ' vector(s) differ from the Python validator');
  Halt(1);
end.
