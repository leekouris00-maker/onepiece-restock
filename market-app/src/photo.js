import { Alert, Platform } from 'react-native';
import * as ImagePicker from 'expo-image-picker';

export async function pickPhoto(onUri) {
  const go = async camera => {
    const fn = camera ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync;
    if (camera) { const p = await ImagePicker.requestCameraPermissionsAsync(); if (!p.granted) return; }
    const r = await fn({ mediaTypes: ['images'], quality: 0.9, allowsEditing: true, aspect: [63, 88] });
    if (!r.canceled && r.assets?.[0]) onUri(r.assets[0].uri);
  };
  if (Alert.alert && Platform.OS !== 'web') Alert.alert('Add a photo', undefined, [{ text: 'Take photo', onPress: () => go(true) }, { text: 'Choose from library', onPress: () => go(false) }, { text: 'Cancel', style: 'cancel' }]);
  else go(false);
}

