using Avalonia.Data.Converters;
using Avalonia.Media;
using System;
using System.Globalization;

namespace Doyen.TestApp
{
    public class StatusColorConverter : IValueConverter
    {
        public static readonly StatusColorConverter Instance = new StatusColorConverter();

        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is bool isConnected)
            {
                return isConnected ? Brushes.Green : Brushes.Red;
            }
            return Brushes.Black;
        }

        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        {
            throw new NotImplementedException();
        }
    }
}