USE [msdb]
GO

/****** Object:  Job [DWH - Nightly Load]    Script Date: 30/09/2026 11:42:10 ******/
BEGIN TRANSACTION
DECLARE @ReturnCode INT
SELECT @ReturnCode = 0
/****** Object:  JobCategory [Data Warehouse]    Script Date: 30/09/2026 11:42:10 ******/
IF NOT EXISTS (SELECT name FROM msdb.dbo.syscategories WHERE name=N'Data Warehouse' AND category_class=1)
BEGIN
EXEC @ReturnCode = msdb.dbo.sp_add_category @class=N'JOB', @type=N'LOCAL', @name=N'Data Warehouse'
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback

END

DECLARE @jobId BINARY(16)
EXEC @ReturnCode =  msdb.dbo.sp_add_job @job_name=N'DWH - Nightly Load',
		@enabled=1,
		@notify_level_eventlog=0,
		@notify_level_email=2,
		@notify_level_netsend=0,
		@notify_level_page=0,
		@delete_level=0,
		@description=N'Nightly staging purge, sales mart refresh and export queue reset',
		@category_name=N'Data Warehouse',
		@owner_login_name=N'CORP\svc_sqlagent',
		@notify_email_operator_name=N'DWH Oncall', @job_id = @jobId OUTPUT
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [Purge staging]    Script Date: 30/09/2026 11:42:10 ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Purge staging',
		@step_id=1,
		@cmdexec_success_code=0,
		@on_success_action=3,
		@on_success_step_id=0,
		@on_fail_action=4,
		@on_fail_step_id=5,
		@retry_attempts=2,
		@retry_interval=5,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'EXEC dbo.usp_purge_stage',
		@database_name=N'SalesDW',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [Load sales mart]    Script Date: 30/09/2026 11:42:10 ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Load sales mart',
		@step_id=2,
		@cmdexec_success_code=0,
		@on_success_action=3,
		@on_success_step_id=0,
		@on_fail_action=4,
		@on_fail_step_id=5,
		@retry_attempts=1,
		@retry_interval=10,
		@os_run_priority=0, @subsystem=N'SSIS',
		@command=N'/ISSERVER "\"\SSISDB\DWH\SalesMart\LoadSalesMart.dtsx\"" /SERVER "\"dwh-sql01\"" /Par "\"$ServerOption::LOGGING_LEVEL(Int16)\"";1 /Par "\"$ServerOption::SYNCHRONIZED(Boolean)\"";True /CALLERINFO SQLAGENT /REPORTING E',
		@database_name=N'master',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [Reset export queue]    Script Date: 30/09/2026 11:42:10 ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Reset export queue',
		@step_id=3,
		@cmdexec_success_code=0,
		@on_success_action=3,
		@on_success_step_id=0,
		@on_fail_action=2,
		@on_fail_step_id=0,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'TRUNCATE TABLE dbo.ExportQueue',
		@database_name=N'SalesDW',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [Start finance export]    Script Date: 30/09/2026 11:42:10 ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Start finance export',
		@step_id=4,
		@cmdexec_success_code=0,
		@on_success_action=1,
		@on_success_step_id=0,
		@on_fail_action=2,
		@on_fail_step_id=0,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'EXEC msdb.dbo.sp_start_job @job_name = N''FIN - Export Extract''',
		@database_name=N'msdb',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [Notify failure]    Script Date: 30/09/2026 11:42:10 ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Notify failure',
		@step_id=5,
		@cmdexec_success_code=0,
		@on_success_action=2,
		@on_success_step_id=0,
		@on_fail_action=2,
		@on_fail_step_id=0,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'EXEC msdb.dbo.sp_send_dbmail @profile_name = N''DWH'', @recipients = N''dwh-oncall@example.com'', @subject = N''DWH nightly load failed''',
		@database_name=N'msdb',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_update_job @job_id = @jobId, @start_step_id = 1
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobschedule @job_id=@jobId, @name=N'Weeknights 02:15',
		@enabled=1,
		@freq_type=8,
		@freq_interval=62,
		@freq_subday_type=1,
		@freq_subday_interval=0,
		@freq_relative_interval=0,
		@freq_recurrence_factor=1,
		@active_start_date=20190101,
		@active_end_date=99991231,
		@active_start_time=21500,
		@active_end_time=235959,
		@schedule_uid=N'7d1c2f0a-1b3e-4c55-9a77-1f2e3d4c5b6a'
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobserver @job_id = @jobId, @server_name = N'(local)'
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
COMMIT TRANSACTION
GOTO EndSave
QuitWithRollback:
    IF (@@TRANCOUNT > 0) ROLLBACK TRANSACTION
EndSave:
GO

/****** Object:  Job [FIN - Export Extract]    Script Date: 30/09/2026 11:42:10 ******/
BEGIN TRANSACTION
DECLARE @ReturnCode INT
SELECT @ReturnCode = 0
DECLARE @jobId BINARY(16)
EXEC @ReturnCode =  msdb.dbo.sp_add_job @job_name=N'FIN - Export Extract',
		@enabled=1,
		@notify_level_eventlog=0,
		@notify_level_email=0,
		@description=N'Month-end GL export for finance',
		@category_name=N'[Uncategorized (Local)]',
		@owner_login_name=N'CORP\svc_sqlagent', @job_id = @jobId OUTPUT
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Extract GL',
		@step_id=1,
		@cmdexec_success_code=0,
		@on_success_action=3,
		@on_success_step_id=0,
		@on_fail_action=2,
		@on_fail_step_id=0,
		@retry_attempts=3,
		@retry_interval=15,
		@os_run_priority=0, @subsystem=N'CmdExec',
		@command=N'dtexec /F "D:\ssis\packages\ExportGL.dtsx" /REP E',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'Archive GL files',
		@step_id=2,
		@cmdexec_success_code=0,
		@on_success_action=1,
		@on_success_step_id=0,
		@on_fail_action=2,
		@on_fail_step_id=0,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'PowerShell',
		@command=N'Move-Item -Path D:\exports\gl\*.csv -Destination \\fileshare\finance\archive',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_update_job @job_id = @jobId, @start_step_id = 1
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobschedule @job_id=@jobId, @name=N'Month start 06:00',
		@enabled=1,
		@freq_type=16,
		@freq_interval=1,
		@freq_subday_type=1,
		@freq_subday_interval=0,
		@freq_relative_interval=0,
		@freq_recurrence_factor=1,
		@active_start_date=20190101,
		@active_end_date=99991231,
		@active_start_time=60000,
		@active_end_time=235959
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobserver @job_id = @jobId, @server_name = N'(local)'
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
COMMIT TRANSACTION
GOTO EndSave
QuitWithRollback:
    IF (@@TRANCOUNT > 0) ROLLBACK TRANSACTION
EndSave:
GO
