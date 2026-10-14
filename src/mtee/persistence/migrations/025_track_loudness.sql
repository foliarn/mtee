-- Loudness measured by Analyze (EBU R128 integrated loudness and sample peak), stored
-- beside the tempo and key of the track. Existing rows keep NULL values and a NULL
-- loudness_version: such a track counts as not fully analyzed until Analyze measures it.
-- Loudness is never written to the tags of the file.
ALTER TABLE track_analysis ADD COLUMN integrated_lufs REAL;
ALTER TABLE track_analysis ADD COLUMN sample_peak_dbfs REAL;
ALTER TABLE track_analysis ADD COLUMN loudness_version INTEGER;
