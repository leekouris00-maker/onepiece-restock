import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from '@expo-google-fonts/manrope';
import { DataProvider } from '../src/data';
import { F, useTheme } from '../src/theme';
import { watchForUpdates } from '../src/update';

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function Root() {
  const [loaded] = useFonts({ Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold });
  useEffect(() => { if (loaded) SplashScreen.hideAsync().catch(() => {}); }, [loaded]);
  useEffect(() => watchForUpdates(), []);
  if (!loaded) return null;
  return <DataProvider><Nav /></DataProvider>;
}

function Nav() {
  const c = useTheme();
  return (
    <>
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
        <Stack.Screen name="movers" options={{ title: 'Market movers' }} />
      </Stack>
    </>
  );
}
