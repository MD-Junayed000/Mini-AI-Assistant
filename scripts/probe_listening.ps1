Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in 8000, 8100, 8101, 8102, 8103 } |
    Select-Object LocalPort, OwningProcess |
    Format-Table -AutoSize