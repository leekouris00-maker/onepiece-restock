import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { BodoniModa_600SemiBold, BodoniModa_500Medium_Italic } from '@expo-google-fonts/bodoni-moda';
import { InterTight_400Regular, InterTight_500Medium, InterTight_600SemiBold, InterTight_700Bold } from '@expo-google-fonts/inter-tight';
import { DataProvider } from '../src/data';
import { F, useTheme } from '../src/theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function Root() {
  const [loaded] = useFonts({ BodoniModa_600SemiBold, BodoniModa_500Medium_Italic, InterTight_400Regular, InterTight_500Medium, InterTight_600SemiBold, InterTight_700Bold });
  useEffect(() => { if (loaded) SplashScreen.hideAsync().catch(() => {}); }, [loaded]);
  if (!loaded) return null;
  return <DataProvider><Nav /></DataProvider>;
}

function Nav() {
  const c = useTheme();
  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{
        headerStyle: { backgroundColor: c.band }, headerTintColor: '#fff', headerShadowVisible: false,
        headerTitleStyle: { fontFamily: F.serif, fontSize: 19 }, headerBackTitle: 'Back', contentStyle: { backgroundColor: c.bg },
      }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="set/[id]" options={{ title: '' }} />
        <Stack.Screen name="card/[k]" options={{ title: '', presentation: 'modal' }} />
        <Stack.Screen name="item/[id]" options={{ title: '', presentation: 'modal' }} />
        <Stack.Screen name="addcard" options={{ title: 'Add a card', presentation: 'modal' }} />
      </Stack>
    </>
  );
}
