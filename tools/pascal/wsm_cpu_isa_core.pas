// SPDX-License-Identifier: LicenseRef-Volnist
unit wsm_cpu_isa_core;

{$mode objfpc}{$H+}

interface

uses
  SysUtils, fpjson;

const
  WSM_CPU_ISA_VERSION = '0.1.2';
  WSM_CPU_ISA_SCHEMA = 'wsm-cpu-isa/1';

type
  EIsaError = class(Exception)
  public
    Code: string;
    constructor Create(const ACode, MessageText: string);
  end;

function DetectArchitecture: string;
function BuildEvidence(const CpuInfoPath, Architecture: string): TJSONObject;

implementation

uses
  Classes, SysUtils, DateUtils, BaseUnix, Unix;

const
  V2Features: array[0..6] of string = (
    'cx16', 'lahf_lm', 'popcnt', 'pni', 'ssse3', 'sse4_1', 'sse4_2'
  );
  V3Features: array[0..8] of string = (
    'avx', 'avx2', 'bmi1', 'bmi2', 'f16c', 'fma', 'abm', 'movbe', 'osxsave'
  );
  V4Features: array[0..4] of string = (
    'avx512f', 'avx512bw', 'avx512cd', 'avx512dq', 'avx512vl'
  );

constructor EIsaError.Create(const ACode, MessageText: string);
begin
  inherited Create(ACode + ': ' + MessageText);
  Code := ACode;
end;

function DetectArchitecture: string;
var
  SystemInfo: UtsName;
begin
  Result := 'unknown';
  FillChar(SystemInfo, SizeOf(SystemInfo), 0);
  if fpUname(SystemInfo) = 0 then
    Result := StrPas(@SystemInfo.Machine[0]);
  if Result = '' then
    Result := 'unknown';
end;

function CurrentTimestampUTC: string;
var
  UnixTime: Int64;
  UTCDate: TDateTime;
begin
  UnixTime := DateTimeToUnix(Now, False);
  UTCDate := UnixToDateTime(UnixTime, True);
  Result := FormatDateTime('yyyy"-"mm"-"dd"T"hh":"nn":"ss"Z"', UTCDate);
end;

function IsX86_64(const Architecture: string): Boolean;
var
  Normalized: string;
begin
  Normalized := LowerCase(Trim(Architecture));
  Result := (Normalized = 'x86_64') or
            (Normalized = 'amd64') or
            (Normalized = 'x86-64');
end;

function ParseFields(const BlockText: string): TStringList;
var
  Lines: TStringList;
  Index, Colon: Integer;
  Key, Value: string;
begin
  Result := TStringList.Create;
  Result.NameValueSeparator := '=';
  Result.CaseSensitive := True;
  Lines := TStringList.Create;
  try
    Lines.Text := BlockText;
    for Index := 0 to Lines.Count - 1 do
    begin
      Colon := Pos(':', Lines[Index]);
      if Colon <= 0 then
        Continue;
      Key := Trim(Copy(Lines[Index], 1, Colon - 1));
      Value := Trim(Copy(Lines[Index], Colon + 1, MaxInt));
      if (Key <> '') and (Result.IndexOfName(Key) < 0) then
        Result.Add(Key + '=' + Value);
    end;
  finally
    Lines.Free;
  end;
end;

procedure SplitCpuInfoBlocks(const Text: string; Blocks: TStrings);
var
  Lines, Current: TStringList;
  Index: Integer;
begin
  Lines := TStringList.Create;
  Current := TStringList.Create;
  try
    Lines.Text := Text;
    for Index := 0 to Lines.Count - 1 do
    begin
      if Trim(Lines[Index]) = '' then
      begin
        if Current.Count > 0 then
        begin
          Blocks.Add(Current.Text);
          Current.Clear;
        end;
      end
      else
        Current.Add(Lines[Index]);
    end;
    if Current.Count > 0 then
      Blocks.Add(Current.Text);
  finally
    Current.Free;
    Lines.Free;
  end;
end;

procedure ReadCpuInfoFlags(const CpuInfoPath: string;
  CommonFlags, FirstProcessorFields: TStrings; out ProcessorCount: Integer);
var
  Content: TStringList;
  Blocks, Tokens, FlagSet: TStringList;
  ParsedBlocks: TList;
  Fields: TStringList;
  Index, TokenIndex, ProcessorBlocks, MissingFlags, FirstProcessorIndex: Integer;
  FlagText, Normalized: string;
  HasCommonFlagSet: Boolean;
begin
  ProcessorCount := 0;
  Content := TStringList.Create;
  Blocks := TStringList.Create;
  Tokens := TStringList.Create;
  FlagSet := TStringList.Create;
  ParsedBlocks := TList.Create;
  try
    Content.NameValueSeparator := '=';
    try
      Content.LoadFromFile(CpuInfoPath);
    except
      on E: Exception do
        raise EIsaError.Create('cpuinfo.unreadable',
          'cannot read ' + CpuInfoPath + ': ' + E.Message);
    end;

    SplitCpuInfoBlocks(Content.Text, Blocks);
    if Blocks.Count = 0 then
      raise EIsaError.Create('cpuinfo.empty',
        CpuInfoPath + ' contains no processor information');

    ProcessorBlocks := 0;
    FirstProcessorIndex := -1;
    for Index := 0 to Blocks.Count - 1 do
    begin
      Fields := ParseFields(Blocks[Index]);
      ParsedBlocks.Add(Fields);
      if Fields.IndexOfName('processor') >= 0 then
      begin
        Inc(ProcessorBlocks);
        if FirstProcessorIndex < 0 then
          FirstProcessorIndex := Index;
      end;
    end;

    if (ProcessorBlocks > 0) and (ProcessorBlocks <> Blocks.Count) then
      raise EIsaError.Create('cpuinfo.processor-block-incomplete',
        IntToStr(Blocks.Count - ProcessorBlocks) + ' non-empty block(s) in ' +
        CpuInfoPath + ' do not identify a processor; refusing to compute a ' +
        'system-wide ISA verdict from partial input');

    if ProcessorBlocks = 0 then
    begin
      if Blocks.Count <> 1 then
        raise EIsaError.Create('cpuinfo.processor-block-incomplete',
          CpuInfoPath + ' contains multiple non-empty blocks but no processor identifiers');
      ProcessorCount := 1;
      FirstProcessorIndex := 0;
    end
    else
      ProcessorCount := ProcessorBlocks;

    Fields := TStringList(ParsedBlocks[FirstProcessorIndex]);
    FirstProcessorFields.Assign(Fields);

    Tokens.Delimiter := ' ';
    Tokens.StrictDelimiter := True;
    FlagSet.Sorted := True;
    FlagSet.Duplicates := dupIgnore;
    FlagSet.CaseSensitive := True;
    CommonFlags.Sorted := True;
    CommonFlags.Duplicates := dupIgnore;
    CommonFlags.CaseSensitive := True;

    MissingFlags := 0;
    HasCommonFlagSet := False;
    for Index := 0 to Blocks.Count - 1 do
    begin
      Fields := TStringList(ParsedBlocks[Index]);
      FlagText := Trim(Fields.Values['flags']);
      if FlagText = '' then
      begin
        Inc(MissingFlags);
        Continue;
      end;

      Normalized := StringReplace(FlagText, #9, ' ', [rfReplaceAll]);
      Tokens.DelimitedText := Normalized;
      FlagSet.Clear;
      for TokenIndex := 0 to Tokens.Count - 1 do
        if Trim(Tokens[TokenIndex]) <> '' then
          FlagSet.Add(Trim(Tokens[TokenIndex]));

      if FlagSet.Count = 0 then
      begin
        Inc(MissingFlags);
        Continue;
      end;

      if not HasCommonFlagSet then
      begin
        CommonFlags.Assign(FlagSet);
        HasCommonFlagSet := True;
      end
      else
      begin
        for TokenIndex := CommonFlags.Count - 1 downto 0 do
          if FlagSet.IndexOf(CommonFlags[TokenIndex]) < 0 then
            CommonFlags.Delete(TokenIndex);
      end;
    end;

    if MissingFlags = ProcessorCount then
      raise EIsaError.Create('cpuinfo.flags-unavailable',
        'no processor block in ' + CpuInfoPath +
        ' exposes a non-empty flags field');
    if MissingFlags > 0 then
      raise EIsaError.Create('cpuinfo.flags-incomplete',
        IntToStr(MissingFlags) + ' of ' + IntToStr(ProcessorCount) +
        ' processor blocks in ' + CpuInfoPath +
        ' do not expose a non-empty flags field; refusing a system-wide ISA verdict');
  finally
    for Index := 0 to ParsedBlocks.Count - 1 do
      TObject(ParsedBlocks[Index]).Free;
    ParsedBlocks.Free;
    FlagSet.Free;
    Tokens.Free;
    Blocks.Free;
    Content.Free;
  end;
end;

function AddLevel(Levels: TJSONObject; const Name: string;
  const Required: array of string; PreviousSupported: Boolean;
  CommonFlags: TStrings; out Supported: Boolean): TJSONObject;
var
  Index: Integer;
  Missing: TJSONArray;
begin
  Missing := TJSONArray.Create;
  for Index := Low(Required) to High(Required) do
    if CommonFlags.IndexOf(Required[Index]) < 0 then
      Missing.Add(Required[Index]);

  Supported := PreviousSupported and (Missing.Count = 0);
  Result := TJSONObject.Create;
  Result.Add('supported', Supported);
  Result.Add('missing', Missing);
  Levels.Add(Name, Result);
end;

function BuildLevels(CommonFlags: TStrings; out Highest: string): TJSONObject;
var
  V2Supported, V3Supported, V4Supported: Boolean;
begin
  Result := TJSONObject.Create;
  AddLevel(Result, 'x86-64-v2', V2Features, True, CommonFlags, V2Supported);
  AddLevel(Result, 'x86-64-v3', V3Features, V2Supported, CommonFlags, V3Supported);
  AddLevel(Result, 'x86-64-v4', V4Features, V3Supported, CommonFlags, V4Supported);

  Highest := 'x86-64-v1';
  if V2Supported then
    Highest := 'x86-64-v2';
  if V3Supported then
    Highest := 'x86-64-v3';
  if V4Supported then
    Highest := 'x86-64-v4';
  Result.Add('highest_supported', Highest);
end;

function BuildEvidence(const CpuInfoPath, Architecture: string): TJSONObject;
var
  CommonFlags, ProcessorFields: TStringList;
  ProcessorCount, Index: Integer;
  Warnings, Limits: TJSONArray;
  Levels, Evidence: TJSONObject;
  Highest, Vendor, ModelName: string;
begin
  if not IsX86_64(Architecture) then
    raise EIsaError.Create('isa.not-x86',
      'x86-64 levels are defined only for x86-64, got ' +
      QuotedStr(Architecture) + '; this evidence does not apply to other architectures');

  CommonFlags := TStringList.Create;
  ProcessorFields := TStringList.Create;
  ProcessorFields.NameValueSeparator := '=';
  try
    ReadCpuInfoFlags(CpuInfoPath, CommonFlags, ProcessorFields, ProcessorCount);
    Vendor := ProcessorFields.Values['vendor_id'];
    ModelName := ProcessorFields.Values['model name'];
    if Vendor = '' then
      Vendor := 'unknown';
    if ModelName = '' then
      ModelName := 'unknown';

    Levels := BuildLevels(CommonFlags, Highest);
    Evidence := nil;
    Warnings := nil;
    Limits := nil;
    try
      Warnings := TJSONArray.Create;
      if CommonFlags.IndexOf('osxsave') < 0 then
        Warnings.Add('osxsave is not exposed in the common kernel flags; an AVX-family level is not confirmed by this evidence');
      if (Vendor <> 'unknown') and (Vendor <> 'GenuineIntel') and
         (Vendor <> 'AuthenticAMD') then
        Warnings.Add('unexpected vendor_id ' + QuotedStr(Vendor) +
          '; levels are computed from exposed features, not from the vendor');

      Limits := TJSONArray.Create;
      Limits.Add('a supported level is evidence about flags exposed by the running kernel, not a silicon inventory or build decision');
      Limits.Add('the /proc/cpuinfo flag list is incomplete; an absent flag does not prove the hardware lacks that feature');
      Limits.Add('the intersection is a conservative set common to all reported logical processors');
      Limits.Add('no performance claim is made: v2-to-v3 gains are workload-dependent');

      Evidence := TJSONObject.Create;
      Evidence.Add('source', 'procfs:' + CpuInfoPath);
      Evidence.Add('kind', 'live-observation');
      Evidence.Add('confidence', 'confirmed');
      Evidence.Add('scope', 'common-kernel-exposed-flags');
      Evidence.Add('logical_processor_count', ProcessorCount);
      Evidence.Add('feature_count', CommonFlags.Count);

      Result := TJSONObject.Create;
      Result.Add('schema', WSM_CPU_ISA_SCHEMA);
      Result.Add('tool_version', WSM_CPU_ISA_VERSION);
      Result.Add('collected_at', CurrentTimestampUTC);
      Result.Add('architecture', Architecture);
      Result.Add('vendor', Vendor);
      Result.Add('model_name', ModelName);
      Result.Add('level_semantics',
        'cumulative x86-64 psABI levels from the intersection of kernel-exposed flags across all processor blocks reported by procfs');
      Result.Add('levels', Levels);
      Levels := nil;
      Result.Add('evidence', Evidence);
      Evidence := nil;
      Result.Add('warnings', Warnings);
      Warnings := nil;
      Result.Add('limits', Limits);
      Limits := nil;
    finally
      Levels.Free;
      Evidence.Free;
      Warnings.Free;
      Limits.Free;
    end;
  finally
    ProcessorFields.Free;
    CommonFlags.Free;
  end;
end;

end.
