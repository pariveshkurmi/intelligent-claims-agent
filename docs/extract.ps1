Add-Type -AssemblyName System.IO.Compression.FileSystem

$docx = 'c:\Users\pariv\Projects\Planner\docs\UHG_FDE_Capstone_Problem_Definition.docx'
$zip = [System.IO.Compression.ZipFile]::OpenRead($docx)
$entry = $zip.GetEntry('word/document.xml')
$stream = $entry.Open()
$reader = New-Object System.IO.StreamReader($stream)
$xmlContent = $reader.ReadToEnd()
$reader.Close()
$stream.Close()
$zip.Dispose()

[xml]$xml = $xmlContent
$ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
$nodes = $xml.SelectNodes('//w:p', $ns)

$lines = [System.Collections.Generic.List[string]]::new()
foreach ($node in $nodes) {
    $tNodes = $node.SelectNodes('.//w:t', $ns)
    $text = ""
    foreach ($t in $tNodes) {
        $text += $t.InnerText
    }
    if ($text.Trim() -ne "") {
        $lines.Add($text.Trim())
    }
}

[System.IO.File]::WriteAllLines('c:\Users\pariv\Projects\Planner\docs\extracted_text.txt', $lines)
Write-Output "Successfully extracted $($lines.Count) lines."

