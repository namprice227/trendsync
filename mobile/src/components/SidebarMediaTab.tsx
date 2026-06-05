import React from 'react';
import { View, Text, StyleSheet, Pressable, Platform, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { MediaItem, UploadProgress } from '../types';
import { Tag } from './Tag';

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  const formatted = index === 0 || value >= 10 ? Math.round(value).toString() : value.toFixed(1);
  return `${formatted} ${units[index]}`;
}

export function SidebarMediaTab({
  mediaItems,
  favoriteClipIds,
  excludedClipIds,
  uploadProgress,
  onUpload,
  onToggleFavorite,
  onToggleExclude,
  onMoveClip,
}: {
  mediaItems: MediaItem[];
  favoriteClipIds: string[];
  excludedClipIds: string[];
  uploadProgress: UploadProgress | null;
  onUpload: () => void;
  onToggleFavorite: (clipId: string) => void;
  onToggleExclude: (clipId: string) => void;
  onMoveClip: (clipId: string, direction: -1 | 1) => void;
}) {
  const uploading = Boolean(uploadProgress);
  const percent = uploadProgress?.percent ?? null;
  const visiblePercent = uploadProgress ? (uploadProgress.phase === 'processing' ? 100 : Math.max(6, percent ?? 6)) : 0;
  const progressWidth = `${visiblePercent}%` as `${number}%`;
  const clipLabel = uploadProgress
    ? `${uploadProgress.fileCount} clip${uploadProgress.fileCount === 1 ? '' : 's'}`
    : '';
  const byteLabel = uploadProgress
    ? uploadProgress.totalBytes
      ? `${formatBytes(uploadProgress.loadedBytes)} / ${formatBytes(uploadProgress.totalBytes)}`
      : uploadProgress.loadedBytes > 0
        ? formatBytes(uploadProgress.loadedBytes)
        : ''
    : '';
  const uploadTitle = !uploadProgress
    ? 'Add clips'
    : uploadProgress.phase === 'processing'
      ? 'Processing clips'
      : percent !== null
        ? `Uploading ${percent}%`
        : 'Uploading clips';
  const uploadSub = !uploadProgress
    ? 'MP4, MOV, M4V, WebM'
    : uploadProgress.phase === 'processing'
      ? `${clipLabel} uploaded, analyzing media`
      : [clipLabel, byteLabel].filter(Boolean).join(', ');

  return (
    <View style={styles.root}>
      {/* Upload zone */}
      <Pressable
        onPress={onUpload}
        disabled={uploading}
        accessibilityState={{ disabled: uploading }}
        style={({ pressed, hovered }: any) => [
          styles.uploadZone,
          uploading && styles.uploadZoneActive,
          hovered && !uploading && styles.uploadZoneHovered,
          pressed && !uploading && styles.uploadZonePressed,
        ]}
      >
        <View style={styles.uploadIcon}>
          {uploading ? (
            <ActivityIndicator size="small" color={colors.blue} />
          ) : (
            <Ionicons name="cloud-upload-outline" size={22} color={colors.blue} />
          )}
        </View>
        <View style={styles.uploadBody}>
          <View style={styles.uploadCopyRow}>
            <View style={styles.uploadCopy}>
              <Text style={styles.uploadTitle}>{uploadTitle}</Text>
              <Text style={styles.uploadSub} numberOfLines={1}>{uploadSub}</Text>
            </View>
            {uploadProgress?.phase === 'processing' ? (
              <Ionicons name="sparkles-outline" size={15} color={colors.blue} />
            ) : null}
          </View>
          <View style={[styles.uploadProgressTrack, !uploading && styles.uploadProgressHidden]}>
            <View style={[styles.uploadProgressFill, { width: progressWidth }]} />
          </View>
        </View>
      </Pressable>

      {/* Clip list */}
      {mediaItems.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="videocam-outline" size={24} color={colors.subtle} />
          <Text style={styles.emptyText}>No clips uploaded yet</Text>
        </View>
      ) : (
        <View style={styles.clipList}>
          <Text style={styles.sectionLabel}>{mediaItems.length} clip{mediaItems.length !== 1 ? 's' : ''}</Text>
          {mediaItems.map((item, index) => {
            const favorite = favoriteClipIds.includes(item.id);
            const excluded = excludedClipIds.includes(item.id);
            const duration = item.analysis?.duration_seconds;
            const quality = item.analysis?.quality_label;
            return (
              <View key={item.id} style={[styles.clipRow, excluded && styles.clipRowExcluded]}>
                <View style={styles.clipThumb}>
                  <Text style={styles.clipIndex}>{index + 1}</Text>
                </View>
                <View style={styles.clipInfo}>
                  <Text style={styles.clipName} numberOfLines={1}>{item.filename}</Text>
                  <View style={styles.clipMeta}>
                    {duration != null ? <Text style={styles.clipDetail}>{Math.round(duration)}s</Text> : null}
                    {quality ? <Tag label={quality} tone={quality === 'dark' || quality === 'soft or shaky' ? 'warning' : 'neutral'} /> : null}
                    {excluded ? <Tag label="excluded" tone="warning" /> : null}
                  </View>
                </View>
                <Pressable onPress={() => onMoveClip(item.id, -1)} disabled={index === 0} style={[styles.iconButton, index === 0 && styles.iconButtonDisabled]}>
                  <Ionicons name="arrow-up" size={15} color={index === 0 ? colors.subtle : colors.muted} />
                </Pressable>
                <Pressable onPress={() => onMoveClip(item.id, 1)} disabled={index === mediaItems.length - 1} style={[styles.iconButton, index === mediaItems.length - 1 && styles.iconButtonDisabled]}>
                  <Ionicons name="arrow-down" size={15} color={index === mediaItems.length - 1 ? colors.subtle : colors.muted} />
                </Pressable>
                <Pressable onPress={() => onToggleFavorite(item.id)} disabled={excluded} style={[styles.iconButton, excluded && styles.iconButtonDisabled]}>
                  <Ionicons
                    name={favorite ? 'star' : 'star-outline'}
                    size={15}
                    color={favorite ? colors.amber : colors.subtle}
                  />
                </Pressable>
                <Pressable onPress={() => onToggleExclude(item.id)} style={styles.iconButton}>
                  <Ionicons
                    name={excluded ? 'eye-off' : 'eye-outline'}
                    size={15}
                    color={excluded ? colors.amber : colors.subtle}
                  />
                </Pressable>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    gap: 10,
  },
  uploadZone: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.blue,
    backgroundColor: colors.surfaceRaised,
    padding: 14,
    ...(Platform.OS === 'web' ? ({ transition: 'all 150ms ease', cursor: 'pointer' } as any) : {}),
  },
  uploadZoneActive: {
    borderColor: colors.blue,
    backgroundColor: colors.blueSoft,
    ...(Platform.OS === 'web' ? ({ cursor: 'progress' } as any) : {}),
  },
  uploadZoneHovered: {
    borderColor: colors.blue,
    backgroundColor: 'rgba(0, 229, 255, 0.06)',
  },
  uploadZonePressed: {
    transform: [{ scale: 0.98 }],
  },
  uploadIcon: {
    width: 40,
    height: 40,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.blueSoft,
  },
  uploadBody: {
    flex: 1,
    minWidth: 0,
    gap: 8,
  },
  uploadCopyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  uploadCopy: {
    flex: 1,
    minWidth: 0,
  },
  uploadTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: '800',
  },
  uploadSub: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '600',
  },
  uploadProgressTrack: {
    height: 5,
    borderRadius: radii.round,
    backgroundColor: colors.lineStrong,
    overflow: 'hidden',
  },
  uploadProgressHidden: {
    opacity: 0,
  },
  uploadProgressFill: {
    height: 5,
    borderRadius: radii.round,
    backgroundColor: colors.blue,
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 32,
    gap: 8,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '700',
  },
  sectionLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  clipList: {
    gap: 4,
  },
  clipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: radii.md,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 10,
    paddingVertical: 8,
    ...(Platform.OS === 'web' ? ({ transition: 'background 120ms ease' } as any) : {}),
  },
  clipRowExcluded: {
    opacity: 0.62,
    backgroundColor: colors.paper,
  },
  clipThumb: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    backgroundColor: colors.paper,
    alignItems: 'center',
    justifyContent: 'center',
  },
  clipIndex: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '900',
  },
  clipInfo: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  clipName: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: '700',
  },
  clipMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  clipDetail: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
  },
  iconButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
  },
  iconButtonDisabled: {
    opacity: 0.45,
  },
});
