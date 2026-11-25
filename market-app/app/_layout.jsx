import React, { useEffect } from 'react';
import { Platform, View } from 'react-native';
import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from '@expo-google-fonts/manrope';
import { DataProvider } from '../src/data';
import { F, useTheme } from '../src/theme';
import { watchForUpdates } from '../src/update';
import { ToastHost } from '../src/toast';
import { FeedbackButton, Tour, useTourStart } from '../src/feedback';
import { KeyHost } from '../src/palette';

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function Root() {
  const [loaded] = useFonts({ Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold });
  useEffect(() => { if (loaded) SplashScreen.hideAsync().catch(() => {}); }, [loaded]);
  useEffect(() => watchForUpdates(), []);
  useEffect(() => registerOffline(), []);
  if (!loaded) return null;
  return <DataProvider><Nav /></DataProvider>;
}

// Keeps the app's own files on the phone so it opens without signal (prices and your collection are saved separately)
function registerOffline() {
  if (Platform.OS !== 'web' || typeof navigator === 'undefined' || !navigator.serviceWorker) return;
  const src = [...document.scripts].map(s => s.src).find(s => s.includes('/_expo/static/js/web/'));
  if (!src) return;                                   // dev server
  const base = src.slice(0, src.indexOf('_expo/'));
  navigator.serviceWorker.register(base + 'sw.js', { scope: base }).catch(() => {});
}

function Nav() {
  const c = useTheme();
  useTourStart();
  return (
    <View style={{ flex: 1 }}>
      <StatusBar style="light" />
      <Stack screenOptions={{
        headerStyle: { backgroundColor: c.bg }, headerTintColor: c.ink, headerShadowVisible: false,
        headerTitleStyle: { fontFamily: F.bold, fontSize: 17 }, headerBackTitle: 'Back', contentStyle: { backgroundColor: c.bg },
      }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="set/[id]" options={{ title: '' }} />
        <Stack.Screen name="card/[k]" options={{ title: '', presentation: 'modal' }} />
        <Stack.Screen name="item/[id]" options={{ title: '', presentation: 'modal' }} />
        <Stack.Screen name="addcard" options={{ title: 'Add a card', presentation: 'modal' }} />
        <Stack.Screen name="scan" options={{ headerShown: false, presentation: 'fullScreenModal', animation: 'fade' }} />
        <Stack.Screen name="spin" options={{ title: '' }} />
        <Stack.Screen name="shop" options={{ title: '' }} />
        <Stack.Screen name="movers" options={{ title: 'Market movers' }} />
        <Stack.Screen name="import" options={{ title: 'Import a collection', presentation: 'modal' }} />
        <Stack.Screen name="watchlist" options={{ title: 'Watchlist' }} />
        <Stack.Screen name="trade" options={{ title: 'Trade calculator' }} />
        <Stack.Screen name="deck" options={{ title: 'Deck price' }} />
        <Stack.Screen name="deals" options={{ title: 'Deal alerts' }} />
        <Stack.Screen name="sales" options={{ title: 'Sales report' }} />
        <Stack.Screen name="sets" options={{ title: 'Set progress' }} />
        <Stack.Screen name="share/[id]" options={{ title: '' }} />
        <Stack.Screen name="help" options={{ title: 'All functions' }} />
      </Stack>
      <FeedbackButton />
      <Tour />
      <KeyHost />
      <ToastHost />
    </View>
  );
}
